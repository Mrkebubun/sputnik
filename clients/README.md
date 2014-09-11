# Sputnik Protocol Documentation

## Overview

The server and client communicate using [​WAMP] (http://wamp.ws/).
This is a derivative of a websocket connection with an additional layer supporting RPC and PubSub.

The default port for websockets is 8000. A typical session runs as follows:

1. The client initiates a connection to the server.
2. The client is not authenticated, so they can only query public data, and subscribe to public feeds.
3. The client authenticates to the server via challenge response.
4. The client is now authenticated and may make private calls.
5. The client is automatically subscribed to several feeds relating to their account.

## RPC Response Format

RPC responses are tuples of two elements. The first element any non-zero value if the RPC call succeeded. It is zero
otherwise. The second element is call specific.

## Denominations

All prices and quantities are stored as integers and transmitted over the network as integers. Read
the denominations specification: https://github.com/MimeticMarkets/sputnik/blob/master/clients/Denominations.md

## Data formats

Certain objects are send to the client. They contain a subset of the information contained in the
corresponding server objects. Each is encoded in JSON.

### contract

```json
{
    ticker: "TICKER"
    description: "short description"
    full_description: "full description"
    contract_type: "futures|prediction|cash_pair|cash"
    tick_size: 1
    lot_size: 1
    denominator: 1
    expiration: "1390165959122754"
}
```

### trade
```json
{
    contract: "TICKER"
    price: 100000
    quantity: 100000
    timestamp: "1390165959122754"
}
```

### ohlcv
```json
{
   contract: "TICKER"
   period: "day|hour|minute"
   open: 4244
   high: 6777
   low: 4000
   close: 5456
   volume: 245
   vwap: 5100
   open_timestamp: "2340934534283"
   close_timestamp: "456945645968"
}
```

### order
```json
{
    contract: "TICKER"
    price: 100000
    quantity: 10000
    quantity_left: 500
    side: "BUY|SELL"
    timestamp: "1390165959122754"
    id: 3123121
    is_cancelled: "True|False"
}
```

### position
```json
{
    contract: "TICKER"
    position: 1000
    reference_price: 1000
}
```

### trade
```json
{
         contract: "TICKER"
         price: 100
         quantity: 100000
         id: 3123121
         timestamp: "234234234"
}
```

### fill
```json
      {
         contract: "TICKER"
         price: 100
         quantity: 100000
         id: 3123121
         timestamp: "234234234"
         side: "BUY|SELL"
         fees: {
            BTC: 24000000
            MXN: 23123
        }
     }
```

### transaction
```json
{
     contract: "TICKER"
     timestamp: "23423423"
     quantity: 23423
     type: "Trade|Transfer|Deposit|Withdrawal|Fee|Adjustment"
     note: "note about the transaction"
     direction: "debit|credit"
}
```

## Public methods

### get_markets()
Take no arguments. Returns a ticker-indexed dictionary of contracts corresponding to currently active markets.

### get_trade_history(ticker, start_timestamp, end_timestamp)

ticker must be a string. It must be one of the active markets. Returns a time sorted array of trades.

### get_ohlcv_history(ticker,period,start_timestamp,end_timestamp)

ticker must be a string. It must be one of the active markets. period is minute/hour/day.
Returns a dict with the key as the timestamp, the start of the period in question.

Each entry is an ```ohlcv``` object

### get_order_book(ticker)

ticker must be a string. It must be one of the active markets. Returns a dictionary with keys 'bids' and 'asks' and
values array of orders. Key ```contract``` is the ticker requested.

### get_chat_history()

Take no arguments. Returns a list of the last 100 chat messages. Each element is in the format [nickname, message].

### get_audit()

Takes no argument. Returns audit data which allows the user to see his balance in each contract (blinded by user_hash)
and the total balance for each contract, so he can verify that there is enough money on account to satisfy withdrawal
requests. The audit a dict of assets and liabilities: ticker-indexed dict of positions on that index, and a total
assets vs total liabilities.

```json
{
    timestamp: "2342342"
    Asset: {}
    Liability: {}
}
```

Each entry in assets and liabilities is ticker-indexed:

```json
{
    contract: "TICKER"
    total: 923423
    positions: []
}
```

Positions is an array of ```(user_hash, position)```

### get_reset_token(username)

Takes a username as an argument, sends that user a token to reset their password.

### make_account(username, password, salt, email, nickname)

Create an account with the given username, password hash, and salt. Also set the user's profile to the passed email and nickname

### change_password_token(username, new_password_hash, token)

Given a password reset token, change the user's password to the new hash. leaves the salt and two factor untouched.

## Public feeds

### book#TICKER
Each event is a complete order book. It has the following format. Each entry in bids/asks is a book_row type.

```json
    {
        contract: "TICKER"
        bids:[]
        asks:[]
    }
```

The book_row type:

```json
{
quantity: 42
price: 43
}
```

### trades#TICKER

Each event is a ```trade```.

### safe_prices#TICKER

Each event is a dictionary. The keys are tickers and the values are the new safe prices.

### ohlcv#TICKER

Each event is an ```ohlcv``` object

### chat

Each event is a chat message in the format [nickname, message]. This feed allows publishing when user is authenticated.

## Private methods

### place_order(order)

order must be an ```order``` object, however the timestamp, id, and quantity_left
are ignored. This returns the order id on success.

### cancel_order(id)

order id must be an integer. It is the id of the order as returned by place_order().

### get_positions()

Returns a ticker-indexed dictionary of positions.

### get_open_orders()

Returns an order id-indexed dictionary of orders.

### get_transaction_history(start_timestamp, end_timestamp)

Returns an array of transaction entries

### get_permissions()

Returns a dict with keys that are the user's permissions and values True or False

### get_profile()

Returns the nickname, email, and audit secret for the user

### change_profile(email, nickname)

Change the email and nickname for the user

### request_support_nonce(type)

Returns the nonce you need to submit a support request to the support ticket server. Type is the type of ticket. Only 'Compliance' is currently supported.

### request_withdrawal(ticker, amount, address)

Send a request to withdraw a certain amount of a cash contract to a given address

### get_new_address(ticker)

Request a new address for sending deposits

### get_current_address(ticker)

Return the currently active address for sending deposits

### get_cookie()

Return the authentication cookie for the user

### logout()

Logout

### get_new_two_factor()

Prepares two factor authentication for an account. Returns the shared secret.

### disable_two_factor(confirmation)

Disables two factor auth for an account. Requires 'confirmation', which is the OTP

### register_two_factor(confirmation)

Enables two factor authentication. The confirmation must be the OTP

### change_password(old_hash, new_hash)

Change the password, confirming that the old_hash matches the current password hash

### get_safe_prices(list of tickers)

Returns the safe prices for the tickers passed in, or if none, returns all safe prices

### chat(message)

Publish 'message' on the chat channel

## Private feeds

### orders#USERNAME

Each event is a ```order``` object. It is meant to update an existing order the client has in memory.

### fills#USERNAME

Each event is a ```fill``` object.

### transactions#USERNAME

Each event updates the user when a balance in their account changes, due to withdrawals, deposits, trades, fees,
transfers, adjustments-- anything. Each event is a ```transaction``` object
