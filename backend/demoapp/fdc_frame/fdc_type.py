import html
import re


class SchemaDefinitionError(Exception):
    """Raised when a schema itself is malformed."""


class RequestValidationError(Exception):
    """Raised when request payload does not satisfy the declared schema."""


class FdcType:
    def __init__(self, *, nullable=False, label=None):
        self.nullable = nullable
        self.label = label

    def _display_name(self):
        return self.label or 'Value'

    def validate(self, value):
        if value is None and self.nullable:
            return None
        return value


class FdcStr(FdcType):
    def __init__(
        self,
        *,
        nullable=False,
        label=None,
        strict_required=False,
        max_length=None,
        pattern=None,
        enum=None,
        strip=False,
        escape_html=False,
    ):
        super().__init__(nullable=nullable, label=label)
        self.strict_required = strict_required
        self.max_length = max_length
        self.pattern = pattern
        self.enum = enum
        self.strip = strip
        self.escape_html = escape_html

    def validate(self, value):
        value = super().validate(value)
        if value is None:
            return None
        if not isinstance(value, str):
            raise RequestValidationError(f'{self._display_name()} must be a string.')
        if self.strip:
            value = value.strip()
        if self.strict_required and not value.strip():
            raise RequestValidationError(f'{self._display_name()} is required.')
        if self.max_length is not None and len(value) > self.max_length:
            raise RequestValidationError(
                f'{self._display_name()} must be at most {self.max_length} characters.'
            )
        if self.enum is not None and value not in self.enum:
            raise RequestValidationError(
                f'{self._display_name()} must be one of: {", ".join(self.enum)}.'
            )
        if self.pattern is not None and re.fullmatch(self.pattern, value) is None:
            raise RequestValidationError(f'{self._display_name()} has an invalid format.')
        if self.escape_html:
            value = html.escape(value, quote=True)
        return value


class FdcInt(FdcType):
    def __init__(self, *, nullable=False, label=None, minimum=None, maximum=None, enum=None):
        super().__init__(nullable=nullable, label=label)
        self.minimum = minimum
        self.maximum = maximum
        self.enum = enum

    def validate(self, value):
        value = super().validate(value)
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise RequestValidationError(f'{self._display_name()} must be an integer.')
        if self.enum is not None and value not in self.enum:
            raise RequestValidationError(
                f'{self._display_name()} must be one of: {", ".join(str(item) for item in self.enum)}.'
            )
        if self.minimum is not None and value < self.minimum:
            raise RequestValidationError(
                f'{self._display_name()} must be greater than or equal to {self.minimum}.'
            )
        if self.maximum is not None and value > self.maximum:
            raise RequestValidationError(
                f'{self._display_name()} must be less than or equal to {self.maximum}.'
            )
        return value


class FdcBool(FdcType):
    def validate(self, value):
        value = super().validate(value)
        if value is None:
            return None
        if not isinstance(value, bool):
            raise RequestValidationError(f'{self._display_name()} must be a boolean.')
        return value
