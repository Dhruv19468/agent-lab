"""Errors the services raise. main.py turns each into a JSON response with the right status code.

Services never import FastAPI: they raise these, and the HTTP layer decides how to answer.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class: a request failed for a reason we can explain to the caller."""

    status_code: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    """The thing asked for doesn't exist (404)."""

    status_code = 404


class ConflictError(AppError):
    """The request clashes with the current state, e.g. a duplicate name (409)."""

    status_code = 409


class BadRequestError(AppError):
    """The request is well-formed JSON but refers to something invalid (400)."""

    status_code = 400
