build:
	rm -rf dist/ build/
	hatch build

publish:
	hatch publish

install:
	pip install .[dev]

	