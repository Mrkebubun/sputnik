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
        def wrapped_f(*args, **kwargs):
            callargs = inspect.getcallargs(f, *args, **kwargs)

            # hack to handle methods
            if "self" in callargs:
                del callargs["self"]

            # json only accepts lists as arrays, not tuples
            for key in callargs:
                if type(callargs[key]) == tuple:
                    callargs[key] = list(callargs[key])

            # validate
            f.validator.validate(callargs)

            f(*args, **kwargs)
        return wrapped_f
    return wrap

@schema("rpc/accountant.json#place_order")
def place_order( username, order):
    pass

if __name__ == "__main__":
    order = {"username":"foo", "price":1000, "quantity":1, "ticker":"BTC1401", "side":"BUY", "timestamp":1407213633486125}

    import time
    start = time.time()
    for i in range(10000):
        place_order("foo", order)
    print (time.time() - start)/10000

