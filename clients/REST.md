# Sputnik REST Protocol

The Sputnik REST protocol provides access to the WAMPv2 API RPC calls. It does not provide access to the
feeds.

The REST endpoint is

https://hostname:8443/api

If the WAMPv2 RPC call is "rpc.trader.place_order", then the REST endpoint is:

https://hostname:8443/api/rpc/trader/place_order

All calls are made with 'POST', with the content of type "application/json".

If a public API call, the content is of this form:

```json
{
    "payload": {}
}
```

Where the payload is the arguments to the WAMPv2 API call. For example, for "rpc.market.get_order_book":

```json
{
    "payload": {
        "contract": "BTC/MXN"
    }
}
```

If making an authenticated call:

```json
{
    "payload": {}
    "auth": {
        "key": "908asdf09as8dfsa",
        "nonce": 2341
    }
}
```

Where 'key' is the api_key retrieved in an `rpc.token.get_new_api_credentials` RPC call.

Furthermore, there must be an additional header with a SHA256 HMAC of the contents, using
the api_secret (similarly, that which is generated in `rpc.token.get_new_api_credentials`)

Sample python code:

```python
def generate_auth_json(self, params, api_key, api_secret):
    nonce = int(time.time() * 1e6)
    params['auth'] = {'nonce': nonce,
                      'key': api_key
    }
    message = json.dumps(params)
    signature = hmac.new(api_secret.encode('utf-8'), msg=message.encode('utf-8'), digestmod=hashlib.sha256)
    signature = signature.hexdigest().upper()
    return (signature, message)
```

