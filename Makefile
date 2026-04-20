.PHONY: lint lint-yaml lint-tekton validate

lint:
	tox

lint-yaml:
	tox -e yamllint

lint-tekton:
	tox -e tekton-lint

validate:
	tox -e validate-kustomize
