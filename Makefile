
build:
	poetry build

venv-prepare:
	python3 -m venv venv
	source venv/bin/activate &&\
		python3 -m pip install mkdocs-material mdx_truly_sane_lists mkdocs  pymdown-extensions

venv-tar-install:
	source venv/bin/activate &&\
		python3 -m pip install ./dist/mkdocs_with_confluence-$(shell poetry version -s).tar.gz

venv-serve-example:
	source venv/bin/activate &&\
		cd ./example && python3 -m mkdocs serve

venv-run: build venv-tar-install venv-serve-example

run_example:
	@docker build -t mkdocs-example -f ./example/Dockerfile --build-arg MKDOCS_TO_CONFLUENCE_PASSWORD=$(shell sops --decrypt ./example/secret.yaml | yq '.JIRA_PASSWORD' ) .
	@docker run -p 8000:8000 mkdocs-example 

lint: 
	@docker run --rm -v ${PWD}:/data cytopia/pylint ./mkdocs_with_confluence/plugin.py


