from demoapp.fdc_frame.fdc_type import FdcBool, FdcInt, FdcStr

ECHO_SCHEMA = {
    'post': {
        'raw_post': {
            'name': FdcStr(label='Name', strict_required=True, max_length=60),
            'age': FdcInt(label='Age', minimum=18, maximum=99),
            'active': FdcBool(label='Active flag'),
            'note?': FdcStr(label='Note', max_length=200),
            'metadata': {
                'source': FdcStr(label='Source', strict_required=True, max_length=30),
            },
            'tags': [FdcStr(label='Tag', strict_required=True, max_length=20)],
        }
    }
}

LOGIN_SCHEMA = {
    'post': {
        'raw_post': {
            'username': FdcStr(
                label='Username',
                strict_required=True,
                max_length=30,
                pattern=r'[A-Za-z0-9_.-]+',
                strip=True,
            ),
            'password': FdcStr(
                label='Password',
                strict_required=True,
                max_length=128,
            ),
        }
    }
}

SECURITY_INSPECTION_SCHEMA = {
    'post': {
        'raw_post': {
            'display_name': FdcStr(
                label='Display name',
                strict_required=True,
                max_length=120,
                strip=True,
                escape_html=True,
            ),
            'lookup_term': FdcStr(
                label='Lookup term',
                strict_required=True,
                max_length=80,
                strip=True,
            ),
            'safe_identifier': FdcStr(
                label='Safe identifier',
                strict_required=True,
                max_length=40,
                pattern=r'[A-Za-z0-9_-]+',
                strip=True,
            ),
        }
    }
}

MODEL_COMPARISON_SCHEMA = {
    'get': {
        'query_string': {
            'term': FdcStr(
                label='Model search term',
                strict_required=True,
                max_length=80,
                strip=True,
            ),
        }
    }
}

VM_ASSOCIATION_CONTEXT_SCHEMA = {
    'get': {
        'query_string': {
            'record_id': FdcInt(label='Selected VM record id', minimum=1),
        }
    }
}

SEARCH_SCHEMA = {
    'get': {
        'query_string': {
            'term': FdcStr(label='Search term', strict_required=True, max_length=40),
            'limit?': FdcInt(label='Limit', minimum=1, maximum=10),
            'active?': FdcBool(label='Active filter'),
        }
    }
}

UPLOAD_SCHEMA = {
    'post': {
        'files': {
            'attachment': {
                'name': FdcStr(
                    label='Attachment name',
                    max_length=120,
                    pattern=r'.+\.(txt|md|json)',
                ),
                'maxsize': 1024 * 1024,
                'content_types': ['text/plain', 'application/json', 'text/markdown'],
            }
        }
    }
}

SYSTEM_OPERATION_STATUS_SCHEMA = {
    'get': {
        'query_string': {
            'operation': FdcStr(
                label='Operation',
                strict_required=True,
                enum=['demo-reboot'],
            ),
        }
    }
}
