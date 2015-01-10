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
    payload: {}
}
```

Where the payload is the arguments to the WAMPv2 API call. For example, for "rpc.market.get_order_book":

```json
{
    payload: {
        contract: 'BTC/MXN'
    }
}
```

If making an authenticated call:

```json
{
    payload: {}
    auth: {
        username: "username"
        api_token: "2349058324509348"
        totp: 'CODE'
    }
}
```

The API token is that retrieved via the RPC call "rpc.token.get_new_api_token". If TOTP is enabled for the account,
then the totp field must be present with the correct code.

The results are the same as in the WAMP API.
