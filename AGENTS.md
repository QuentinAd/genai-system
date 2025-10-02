# Guidelines for Generative AI Developers

This repository contains a data pipeline service, a backend service, and infrastructure code. The backend service provides a Quart web application using Blueprints, asyncio, httpx, Gunicorn, and LangChain for streaming chatbots.

Follow the rules in this document when creating or modifying code anywhere in the repository.

## General Workflow

* **Test Driven Development (TDD)**: Write or update tests with pytest for every new feature or bug fix before implementing the code.
* **Linting and Formatting**: Use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. Run `ruff format .` followed by `ruff check .` before committing.
* **Keep it Simple (KISS)**: Prefer simple, readable solutions over complex ones. Avoid unnecessary abstractions.
* **Don't Repeat Yourself (DRY)**: Reuse existing functions and modules whenever possible.
* **Documentation**: Add clear docstrings to modules, classes and functions. Update READMEs when behavior changes.
* **Git Practices**: Keep commits focused and descriptive. Do not amend or force push existing commits.

## Testing

* Run `pytest` from the repository root. Tests live in service directories such as `data-pipeline/tests` and `app/tests`.
* If adding a new service, place its tests in `<service>/tests` and ensure they run with the root `pytest` command.
* Keep tests isolated and deterministic. Use fixtures for setup/teardown logic.

## Data Pipeline Service

* Located in `data-pipeline/`. Use Airflow DAGs to process data stored locally in `data-pipeline/data`.
* Add unit tests in `data-pipeline/tests` for DAG code logic.

## Backend Service

* Located in `app/`. This service is a Quart application using Blueprints, asyncio, httpx, Gunicorn, and LangChain.
* It enables streaming conversational AI via OpenAI models and implements token streaming using asynchronous generator functions.
* Demonstrate Python best practices: classes, inheritance, dunder methods like `__**init**__` where appropriate, decorators, and robust input validation.
* Tests for the backend must mock network calls and cover asynchronous routes.

## Infrastructure Code

* Terraform files reside under `infra/`. Use the provided GitHub workflows for provisioning.
* Validate changes with `terraform validate` and `terraform plan` before applying.

Adhering to these instructions ensures consistent quality across contributions made by generative AI or humans.
