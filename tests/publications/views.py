from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Author, Book
from .serializers import AuthorSerializer, BookSerializer


class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer

    @action(detail=True, methods=["patch"])
    def update_experience(self, request, pk=None):
        """Custom action to update author experience"""
        author = self.get_object()
        experience = request.data.get("experience", "")
        author.experience = experience
        author.save()
        serializer = self.get_serializer(author)
        return Response(serializer.data)


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer

    @action(detail=True, methods=["patch"])
    def update_title(self, request, pk=None):
        """Custom action to update book title"""
        book = self.get_object()
        title = request.data.get("title", "")
        book.title = title
        book.save()
        serializer = self.get_serializer(book)
        return Response(serializer.data)
