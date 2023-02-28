
build:
	poetry build

venv:
	python3 -m venv /tmp/venv

run_example:
	
	@docker build -t mkdocs-example -f ./example/Dockerfile --build-arg MKDOCS_TO_CONFLUENCE_PASSWORD=$(shell sops --decrypt ./example/secret.yaml | yq '.JIRA_PASSWORD' ) .
	@docker run -p 8000:8000 mkdocs-example 

lint: 
	@docker run --rm -v ${PWD}:/data cytopia/pylint ./mkdocs_with_confluence/plugin.py


