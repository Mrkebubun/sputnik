import config
import os
import inspect
import json
import jsonschema
import jsonschema.compat

class RPCSchemaException(Exception):
    pass

# urldefrag

def validate(x, full_uri):
    uri, fragment = jsonschema.compat.urldefrag(full_uri)
    schema_root = config.get("specs", "schema_root")
    with open(os.path.join(schema_root, uri)) as schema_file:
        top_schema = json.load(schema_file)
    resolver = jsonschema.RefResolver("file://" + schema_root + "/", top_schema)
    schema = resolver.resolve_fragment(top_schema, fragment)
    jsonschema.Draft4Validator.check_schema(schema)
    validator = jsonschema.Draft4Validator(schema, resolver=resolver)
    validator.validate(x)


def validator(full_uri):
    uri, fragment = jsonschema.compat.urldefrag(full_uri)
    schema_root = config.get("specs", "schema_root")
    with open(os.path.join(schema_root, uri)) as schema_file:
        top_schema = json.load(schema_file)
    resolver = jsonschema.RefResolver("file://" + schema_root + "/", top_schema)
    schema = resolver.resolve_fragment(top_schema, fragment)
    jsonschema.Draft4Validator.check_schema(schema)
    return jsonschema.Draft4Validator(schema, resolver=resolver)

def schema(path):
    def wrap(f):
        f.schema = path
        f.validator = validator(path)
        if inspect.ismethod(f):
            def wrapped_f(*args, **kwargs):
                validate_method(f, *args, **kwargs)
                f(*args, **kwargs)
        else:
            def wrapped_f(*args, **kwargs):
                validate_function(f, *args, **kwargs)
                f(*args, **kwargs)
        return wrapped_f
    return wrap

def validate_function(f, *args, **kwargs):
    callargs = inspect.getcallargs(f, *args, **kwargs)

    # json only accepts lists as arrays, not tuples
    for key in callargs:
        if type(callargs[key]) == tuple:
            callargs[key] = list(callargs[key])

    f.validator.validate(callargs)


def validate_method(f, *args, **kwargs):
    callargs = inspect.getcallargs(f, None, *args, **kwargs)
    del callargs["self"]

    # json only accepts lists as arrays, not tuples
    for key in callargs:
        if type(callargs[key]) == tuple:
            callargs[key] = list(callargs[key])
    
    f.validator.validate(callargs)


@schema("rpc/accountant.json#place_order")
def place_order(username, order):
    pass

if __name__ == "__main__":
    order = {"username":"foo", "price":1000, "quantity":1, "ticker":"BTC1401", "side":"BUY", "timestamp":1407213633486125}

    place_order("foo", order)

