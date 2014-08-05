import config
import os
import inspect
import json
import jsonschema

class RPCSchemaException(Exception):
    pass

# urldefrag

def validate(x, name):
    schema_root = config.get("specs", "schema_root")
    with open(os.path.join(schema_root, name)) as schema_file:
        schema = json.load(schema_file)
    resolver = jsonschema.RefResolver("file://" + schema_root, schema)
    validator = jsonschema.Draft4Validator(schema, resolver=resolver)
    validator.validate(x)

def schema(path):
    def wrap(f):
        f.schema = path
        return f
    return wrap

def validate_call(f, *args, **kwargs):
    if not hasattr(f, "schema"):
        raise RPCSchemaException("No schema associated with method.")

    if inspect.ismethod(f):
        callargs = inspect.getcallargs(f, None, *args, **kwargs)
        del callargs["self"]
    else:
        callargs = inspect.getcallargs(f, *args, **kwargs)

    # json only accepts lists as arrays, not tuples
    for key in callargs:
        if type(callargs[key]) == tuple:
            callargs[key] = list(callargs[key])

    validate(callargs, f.schema)

@schema("rpc/test.json")
def test(foo):
    pass

