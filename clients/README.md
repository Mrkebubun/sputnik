# Sputnik Protocol Documentation

## Overview

The server and client communicate using [​WAMPv2] (http://wamp.ws/).
This is a derivative of a websocket connection with an additional layer supporting RPC and PubSub.

The default port for websockets is 8443. A typical session runs as follows:

1. The client initiates a connection to the server.
2. The client is not authenticated, so they can only query public data, and subscribe to public feeds.
3. The client authenticates to the server via challenge response.
4. The client is now authenticated and may make private calls.
5. The client is automatically subscribed to several feeds relating to their account.

The websockets endpoint is:

wss://hostname:8443/ws

For information on the REST api, see REST.md

## RPC Response Format

RPC responses are json objects with two elements. In the case of a successful call:

```json
{
    "success": true,
    "result": {}
}
```

In the case of a failure

```json
{
    "success": false,
    "error": ["error-message", "arguments"]
}
```

Error is a list where the first argument is a string specifying the error. Subsequent elements are particular
details about that specific error, for example the invalid data passed to the function.

## Denominations

All prices and quantities are stored as integers and transmitted over the network as integers. Read
the denominations specification: https://github.com/MimeticMarkets/sputnik/blob/master/clients/Denominations.md

## Data formats

Certain objects are send to the client. They contain a subset of the information contained in the
corresponding server objects. Each is encoded in JSON.

### contract

| Name | Type | Description |
|------|------|-------------|
|contract|string|The ticker symbol of the contract|
|description|string|Short description of the contract|
|full_description|string|Full description of the contract|
|contract_type|enum|The type of the contract|
|tick_size|integer|See Denominations spec|
|lot_size|integer|See Denominations spec|
|denominator|integer|See Denominations spec|
|expiration|integer|Contract expiry (Microseconds since epoch)|

Example:

```json
{
    "contract": "TICKER",
    "description": "short description",
    "full_description": "full description",
    "contract_type": "futures|prediction|cash_pair|cash",
    "tick_size": 1,
    "lot_size": 1,
    "denominator": 1,
    "expiration": 1390165959122754
}
```

### trade

| Name | Type | Description |
|------|------|-------------|
|contract|string|The ticker symbol of the contract|
|price|integer|price of the trade|
|quantity|integer|quantity traded|
|timestamp|integer|time of trade (Microseconds since epoch)

```json
{
    "contract": "TICKER",
    "price": 100000,
    "quantity": 100000,
    "timestamp": 1390165959122754
}
```

### ohlcv


| Name | Type | Description |
|------|------|-------------|
|contract|string|The ticker symbol of the contract|
|period|enum|Period for the OHLCV bar|
|open|integer|Opening trade price|
|high|integer|Highest trade price|
|low|integer|Lowest trade price|
|close|integer|Closing trade price|
|volume|integer|Total volume for period|
|vwap|integer|Volume-weighted average price|
|open_timestamp|integer|Beginning of period (Microseconds since epoch)|
|close_timestamp|integer|End of period (Microseconds since epoch)|

```json
{
   "contract": "TICKER",
   "period": "day|hour|minute",
   "open": 4244,
   "high": 6777,
   "low": 4000,
   "close": 5456,
   "volume": 245,
   "vwap": 5100,
   "open_timestamp": 2340934534283,
   "close_timestamp": 456945645968
}
```

### order


| Name | Type | Description |
|------|------|-------------|
|contract|string|The ticker symbol of the contract|
|price|integer|The limit price|
|quantity|integer|Original quantity of the order|
|quantity_left|integer|Remaining unfilled quantity|
|side|enum|Buy or sell|
|timestamp|integer|Timestamp of the order (Microseconds since epoch)|
|id|integer|Order id|
|is_cancelled|boolean|True if the order has been cancelled|

Example: 

```json
{
    "contract": "TICKER",
    "price": 100000,
    "quantity": 10000,
    "quantity_left": 500,
    "side": "BUY|SELL",
    "timestamp": 1390165959122754,
    "id": 3123121,
    "is_cancelled": false,
}
```

### position

| Name | Type | Description |
|------|------|-------------|
|contract|string|The ticker symbol of the contract|
|position|integer|Quantity held|
|reference_price|integer|See futures margin explanation|

Example:

```json
{
    "contract": "TICKER",
    "position": 1000,
    "reference_price": 1000
}
```

### fill


| Name | Type | Description |
|------|------|-------------|
|contract|string|The ticker symbol of the contract|
|price|integer|Price at which the contract traded|
|quantity|integer|Quantity traded|
|id|integer|Trade id|
|timestamp|integer|Timestamp of the trade (Microseconds since epoch)|
|side|enum|Buy or sell|
|fees|dict|Ticker-indexed dict of fees charged|

Example: 

```json
      {
         "contract": "TICKER",
         "price": 100,
         "quantity": 100000,
         "id": 3123121,
         "timestamp": 334234234,
         "side": "BUY|SELL",
         "fees": {
            "BTC": 24000000,
            "MXN": 23123
        }
     }
```

### transaction
| Name | Type | Description |
|------|------|-------------|
|contract|string|The ticker symbol of the contract|
|timestamp|integer|Timestamp of transaction (Microseconds since epoch)|
|quantity|integer|Quantity of the transaction|
|type|enum|Type of transaction|
|note|string|Unstructured description of transaction (future: will be JSON)|
|direction|enum|debit or credit|
|balance|integer|balance after transaction posted|

Example:

```json
{
     "contract": "TICKER",
     "timestamp": 23423423,
     "quantity": 23423,
     "type": "Trade|Transfer|Deposit|Withdrawal|Fee|Adjustment",
     "note": "note about the transaction",
     "direction": "debit|credit",
     "balance": 234523,
}
```

### profile

|Name|Type|Description|
|----|----|-----------|
|email|string|Email address|
|nickname|string|Nickname for user|
|audit_secret|string|Secret to use for audit|
|locale|string|locale string|
|notifications|dict|Notification-type indexed dict. Elements are array of notification method|

```json
{
    "email": "email@domain.com",
    "nickname": "user nickname",
    "audit_secret": "SECRET_USED_FOR_AUDITING",
    "locale": "en",
    "notifications": {
        "fill": ["email", "sms"],
        "order": ["sms"],
        "transaction": ["growl"]
    }
}
```

In the profile object, the notifications is an object which contains elements that configure what notifications
the user would like to receive, and how.

## Public methods

### rpc.market.get_markets()
Take no arguments. Returns a ticker-indexed dictionary of contracts corresponding to currently active markets.

### rpc.info.get_exchange_info()
Takes no arguments. Gets information about the exchange running here.

### rpc.market.get_trade_history(contract, start_timestamp, end_timestamp)

contract must be a string. It must be one of the active markets. Returns a time sorted array of trades.

### rpc.market.get_ohlcv_history(contract, period, start_timestamp,end_timestamp)

contract must be a string. It must be one of the active markets. period is minute/hour/day.
Returns a dict with the key as the timestamp, the start of the period in question.

Each entry is an ```ohlcv``` object

### rpc.market.get_order_book(contract)

contract must be a string. It must be one of the active markets. Returns a dictionary with keys 'bids' and 'asks' and
values array of orders. Key ```contract``` is the contract requested.

### rpc.market.get_safe_prices(list of contracts)

Returns the safe prices for the contracts passed in, or if none, returns all safe prices

### rpc.info.get_audit()

Takes no argument. Returns audit data which allows the user to see his balance in each contract (blinded by user_hash)
and the total balance for each contract, so he can verify that there is enough money on account to satisfy withdrawal
requests. The audit a dict of assets and liabilities: ticker-indexed dict of positions on that index, and a total
assets vs total liabilities.

|Name|Type|Description|
|----|----|-----------|
|timestamp|integer|Timestamp of this audit (Microseconds since epoch)
|Asset|dict|Ticker-indexed dict of assets in balance sheet|
|Liability|dict|Ticked-indexed dict of liabilities in balance sheet|

Example:

```json
{
    "timestamp": 2342342,
    "Asset": {},
    "Liability": {}
}
```

Each entry in assets and liabilities is ticker-indexed:

| Name | Type | Description |
|------|------|-------------|
|contract|string|The ticker symbol of the contract|
|total|integer|Total value|
|positions|array|Array of user positions|

Example:

```json
{
    "contract": "TICKER",
    "total": 923423,
    "positions": []
}
```

Positions is an array of ```(user_hash, position)```

### rpc.registrar.get_reset_token(username)

Takes a username as an argument, sends that user a token to reset their password.

### rpc.registrar.make_account(username, password, salt, email, nickname)

Create an account with the given username, password hash, and salt. Also set the user's profile to the passed email and nickname

### rpc.registrar.change_password_token(username, new_password_hash, token)

Given a password reset token, change the user's password to the new hash. leaves the salt and two factor untouched.

## Public feeds

For the following, TICKER is the ticker with '/' replaced by '_'

### feeds.market.book.TICKER
Each event is a complete order book. It has the following format. Each entry in bids/asks is a book_row type.

| Name | Type | Description |
|------|------|-------------|
|contract|string|The ticker symbol of the contract|
|bids|array|List of book_row|
|asks|array|List of book_row|

Example:

```json
    {
        "contract": "TICKER",
        "bids":[],
        "asks":[]
    }
```

The book_row type:

|Name|Type|Description|
|----|----|-----------|
|quantity|integer|size|
|price|integer|price|

Example:

```json
{
"quantity": 42,
"price": 43
}
```

### feeds.market.trades.TICKER

Each event is a ```trade```.

### feeds.market.safe_prices.TICKER

Each event is a dictionary. The keys are tickers and the values are the new safe prices.

### feeds.market.ohlcv.TICKER

Each event is an ```ohlcv``` object

## Private methods

### rpc.trader.place_order(order)

order must be an ```order``` object, however the timestamp, id, and quantity_left
are ignored. This returns the order id on success.

### rpc.trader.cancel_order(id)

id must be an integer. It is the id of the order as returned by place_order().

### rpc.trader.get_positions()

Returns a ticker-indexed dictionary of positions.

### rpc.trader.get_open_orders()

Returns an order id-indexed dictionary of orders.

### rpc.trader.get_transaction_history(start_timestamp, end_timestamp)

Returns an array of transaction entries

### rpc.trader.get_permissions()

Returns a dict with keys that are the user's permissions and values True or False

### rpc.trader.get_profile()

Returns the profile for the user as a ```profile``` object

### rpc.trader.change_profile(profile)

Change the profile for the user, pass in a ```profile``` object

### rpc.trader.request_support_nonce(type)

Returns the nonce you need to submit a support request to the support ticket server. Type is the type of ticket. Only 'Compliance' is currently supported.

### rpc.trader.request_withdrawal(contract, amount, address)

Send a request to withdraw a certain amount of a cash contract to a given address

### rpc.trader.get_new_address(contract)

Request a new address for sending deposits

### rpc.trader.get_current_address(contract)

Return the currently active address for sending deposits

### rpc.token.get_cookie()

Return the authentication cookie for the user

### rpc.token.change_password(old_hash, new_hash)

Change the password, confirming that the old_hash matches the current password hash

### rpc.token.logout()

Logout

### rpc.token.get_new_api_credentials(expiration)

Get a new set of API credentials and invalidate the old one. If expiration is passed in, then the token will expire at
the expiration (microseconds since epoch). If no expiration is passed in the token will expire in 7 days. In the future
this call will also require an OTP if that is enabled for the account.

Returns

|Name|Type|Description|
|----|----|-----------|
|key|string|User API Key|
|secret|string|User API Secret|

Example:

```json
{
   "key": "sdf98sca",
   "secret": "ac09dancakl"
}
```

### rpc.token.get_new_two_factor()

Prepares two factor authentication for an account. Returns the shared secret.

### rpc.token.disable_two_factor(confirmation)

Disables two factor auth for an account. Requires 'confirmation', which is the OTP

### rpc.token.register_two_factor(confirmation)

Enables two factor authentication. The confirmation must be the OTP

## Private feeds

In the below, USER_HASH is a hex_encoded sha256 hash of the username

### feeds.user.orders.USER_HASH

Each event is a ```order``` object. It is meant to update an existing order the client has in memory.

### feeds.user.fills.USER_HASH

Each event is a ```fill``` object.

### feeds.user.transactions.USER_HASH

Each event updates the user when a balance in their account changes, due to withdrawals, deposits, trades, fees,
transfers, adjustments-- anything. Each event is a ```transaction``` object, but without the `balance` field.

