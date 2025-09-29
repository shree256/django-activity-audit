import inspect
import logging

from functools import wraps
from typing import Any, List, Optional

from django.apps import apps
from django.db import models
from django.db.models.signals import (
    m2m_changed,
    post_delete,
    pre_delete,
    pre_save,
)
from django.dispatch import receiver
from django.forms.models import model_to_dict

from .middleware import get_user_details
from .settings import UNREGISTERED_CLASSES

logger = logging.getLogger("audit.model")

EVENT_TYPES = [
    "CREATE",
    "UPDATE",
    "DELETE",
    "BULK_CREATE",
    "BULK_UPDATE",
    "M2M",
    "PRE_CREATE",
    "PRE_UPDATE",
    "PRE_DELETE",
]


def should_audit(instance):
    """Return True or False to indicate whether the instance should be audited."""
    # do not audit any model listed in UNREGISTERED_CLASSES
    for unregistered_class in UNREGISTERED_CLASSES:
        if isinstance(instance, unregistered_class):
            return False
    return True


def get_calling_model() -> Optional[str]:
    """Get the model name from the calling function's frame."""
    try:
        # Get the current frame
        frame = inspect.currentframe()
        # Go up 3 frames to get to the actual calling function
        # (1 for get_calling_model, 1 for the signal handler, 1 for the bulk operation)
        for _ in range(3):
            frame = frame.f_back
            if frame is None:
                return None

        # Get the calling function's name
        calling_function = frame.f_code.co_name
        # Get the module name
        module_name = frame.f_globals.get("__name__", "")

        # Check if this is a direct bulk operation call
        if "bulk_create" in calling_function or "bulk_update" in calling_function:
            return module_name.split(".")[-1]
    except Exception:
        pass
    return None


class ModelSignalMixin:
    """Mixin to add signal handling capabilities to models."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._original_m2m = self._get_m2m_state()

    def _get_m2m_state(self) -> dict:
        try:
            """Get the current state of M2M fields."""
            return {
                field.name: set(
                    getattr(self, field.name).all().values_list("id", flat=True)
                )
                for field in self._meta.many_to_many
            }
        except Exception as e:
            logger.error(f"Error getting M2M state: {e}")
            return {}


def push_log(
    message: str,
    model: str,
    event_type: str,
    instance_id: str,
    instance_repr: str,
    extra: dict = {},
) -> None:
    user_id, user_info = get_user_details()
    payload: dict = {
        "model": model,
        "instance_id": str(instance_id),
        "event_type": event_type,
        "user_id": user_id,
        "user_info": user_info,
        "instance_repr": instance_repr,
        "extra": extra,
    }

    logger.audit(message, extra=payload)


def patch_model_event(model_class: type[models.Model]) -> None:
    """Monkey patch a model to add signal handling capabilities."""

    if not issubclass(model_class, ModelSignalMixin):
        # Add the mixin to the model's base classes
        model_class.__bases__ = (ModelSignalMixin,) + model_class.__bases__

        # Store the original methods
        original_save = model_class.save
        original_bulk_create = models.QuerySet.bulk_create
        original_bulk_update = models.QuerySet.bulk_update

        # SAVE ---------------------------------------------------------------------------
        @wraps(original_save)
        def save_with_signals(self: models.Model, *args: Any, **kwargs: Any) -> None:
            is_new = self._state.adding

            # Call the original save method
            original_save(self, *args, **kwargs)

            # Log the event
            event_type = EVENT_TYPES[0] if is_new else EVENT_TYPES[1]

            instance_repr = model_to_dict(self)

            push_log(
                f"{event_type} event for {model_class.__name__} (id: {self.pk})",
                model_class.__name__,
                event_type,
                str(self.pk),
                instance_repr,
            )

        # PRE_SAVE ----------------------------------------------------------------------
        @receiver(pre_save, sender=model_class)
        def handle_pre_save(
            sender: type[models.Model], instance: models.Model, **kwargs: Any
        ) -> None:
            if not should_audit(instance):
                return

            is_new = instance._state.adding
            event_type = (
                EVENT_TYPES[6] if is_new else EVENT_TYPES[7]
            )  # PRE_CREATE or PRE_UPDATE

            # For new instances, we might not have a pk yet, so use a placeholder
            instance_id = str(instance.pk) if instance.pk else "pending"
            instance_repr = model_to_dict(instance)

            push_log(
                f"{event_type} event for {model_class.__name__} (id: {instance_id})",
                model_class.__name__,
                event_type,
                instance_id,
                instance_repr,
            )

        # BULK --------------------------------------------------------------------------
        @wraps(original_bulk_create)
        def bulk_create_with_signals(
            self, objs: List[models.Model], *args: Any, **kwargs: Any
        ) -> List[models.Model]:
            if not objs:
                return original_bulk_create(self, objs, *args, **kwargs)

            # Get the calling model
            calling_model = get_calling_model()
            if not calling_model:
                return original_bulk_create(self, objs, *args, **kwargs)

            # Call the original bulk_create method
            created_objs = original_bulk_create(self, objs, *args, **kwargs)

            # Log only if this is the calling model
            if calling_model == model_class.__name__:
                first_obj = created_objs[0]
                instance_repr = model_to_dict(first_obj)

                push_log(
                    f"{EVENT_TYPES[3]} event for {model_class.__name__} (id: {first_obj.pk})",
                    model_class.__name__,
                    EVENT_TYPES[3],
                    str(first_obj.pk),
                    instance_repr,
                    {
                        "total_count": len(created_objs),
                    },
                )

            return created_objs

        @wraps(original_bulk_update)
        def bulk_update_with_signals(
            self, objs: List[models.Model], fields: List[str], batch_size=None
        ) -> None:
            if not objs:
                return original_bulk_update(self, objs, fields, batch_size)

            # Call the original bulk_update method
            original_bulk_update(self, objs, fields, batch_size)

            # Get the calling model
            calling_model = get_calling_model()
            if not calling_model:
                return original_bulk_update(self, objs, fields, batch_size)

            # Log only if this is the calling model
            if calling_model == model_class.__name__:
                first_obj = objs[0]
                instance_repr = model_to_dict(first_obj)

                push_log(
                    f"{EVENT_TYPES[4]} event for {model_class.__name__}",
                    model_class.__name__,
                    EVENT_TYPES[4],
                    str(first_obj.pk),
                    instance_repr,
                    {
                        "total_count": len(objs),
                        "fields": fields,
                    },
                )

        # Replace the methods
        model_class.save = save_with_signals
        models.QuerySet.bulk_create = bulk_create_with_signals
        models.QuerySet.bulk_update = bulk_update_with_signals

        # DELETE -----------------------------------------------------------------------
        @receiver(pre_delete, sender=model_class)
        def handle_pre_delete(
            sender: type[models.Model], instance: models.Model, **kwargs: Any
        ) -> None:
            if not should_audit(instance):
                return

            instance_repr = model_to_dict(instance)

            push_log(
                f"{EVENT_TYPES[8]} event for {model_class.__name__} (id: {instance.pk})",
                model_class.__name__,
                EVENT_TYPES[8],  # PRE_DELETE
                str(instance.pk),
                instance_repr,
            )

        # Add delete signal handling
        @receiver(post_delete, sender=model_class)
        def handle_delete(
            sender: type[models.Model], instance: models.Model, **kwargs: Any
        ) -> None:
            instance_repr = model_to_dict(instance)

            push_log(
                f"{EVENT_TYPES[2]} event for {model_class.__name__} (id: {instance.pk})",
                model_class.__name__,
                EVENT_TYPES[2],
                str(instance.pk),
                instance_repr,
            )

        # M2M ------------------------------------------------------------------------
        for field in model_class._meta.many_to_many:

            @receiver(m2m_changed, sender=getattr(model_class, field.name).through)
            def handle_m2m_changed(
                sender: type[models.Model],
                instance: models.Model,
                action: str,
                pk_set: set,
                **kwargs: Any,
            ) -> None:
                if action not in ["post_add", "post_remove", "post_clear"]:
                    return

                field_name = kwargs.get("model", sender).__name__.lower()
                instance_repr = model_to_dict(instance)

                push_log(
                    f"M2M {action} event for {model_class.__name__} (id: {instance.pk})",
                    model_class.__name__,
                    EVENT_TYPES[5],
                    str(instance.pk),
                    instance_repr,
                    {
                        "field_name": field_name,
                        "related_ids": list(map(str, pk_set)) if pk_set else None,
                    },
                )


def setup_model_signals() -> None:
    """Set up signals for all models in the project."""
    for app_config in apps.get_app_configs():
        for model in app_config.get_models():
            if not should_audit(model):
                continue

            if not issubclass(model, ModelSignalMixin):
                patch_model_event(model)


# Initialize signals when the module is imported
setup_model_signals()
