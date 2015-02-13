# Sputnik Python Clients

Use all code herein at your own risk!

## International Liquidity Pool

The ILP is a marketmaker to augment liquidity in Sputnik exchanges by taking liquidity from non-Sputnik exchanges
and pooling liquidity among Sputnik exchanges.

The initial version only supports taking liquidity from a single exchange and providing liquidity on a single exchange
in a single contract.

### Installation

```
git clone https://github.com/MimeticMarkets/sputnik
sudo apt-get install python-pip
sudo pip install Twisted
sudo pip install autobahn
sudo pip install treq
sudo pip install pycrypto
sudo pip install pyee
cd sputnik/clients/python
```

### Configuration

In `ilp_example_config` there are sample configuration files. Copy one of these to `ilp.ini` and edit as needed.

#### modules

In this configuration section we configure which python modules we use to connect to the source, target, and fiat
exchanges. The fiat "exchange" is only used to get current and historical fiat exchange rates, so it doesn't need
to implement the entire interface documented below.

#### source_connection / target_connection

|Key|Description|
|---|-----------|
|endpoint|The API endpoint|
|id|the client_id/username/api_key|
|secret|the client password/api_secret|

#### tickers

|Key|Description|
|---|-----------|
|source|The fiat currency at the source exchange|
|target|The fiat currency at the target exchange|
|btc|the ticker for bitcoin|

#### target_balance_source / target_balance_target

For each ticker held at the source and target exchanges, what is the ideal balance that we 
want to hold (denominated in their respective currencies)

#### valuation

|Key|Description|
|---|-----------|
|deviation_penalty|How much do we want to punish deviating from our target balances (dimensionless factor)|
|risk_aversion|How afraid are we of volatility (unit: 1/source-currency)|

#### data

Costs here can be artificially inflated if deemed appropriate.

|Key|Description|
|---|-----------|
|fiat_exchange_cost|fixed, variable costs of transferring fiat source<->target (fixed cost in source currency)|
|fiat_exchange_delay|delay of a fiat transfer in seconds (not used)|
|source_fee|fixed, variable costs of executing a trade on source exchange|
|target_fee|fixed, variable costs of executing a trade on fiat exchange|
|btc_fee|btc network transaction fee|
btc_delay|delay of a bitcoin transfer in seconds (not used)|
|variance_period|"day" (only 'day' is supported) - what is the timeframe used to calculate variance|
|variance_window|"month" (only 'month' is supported) - how far to look back to calculate variance|

#### variance_overrides

Normally on startup the ILP downloads historical data to get variances. This may take a while,
so we can override that by fixing the variance for a given contract in this section of the configuration.

#### trader

|Key|Description|
|---|-----------|
|quote_size|What are the size of our quotes (in BTC)|
|out_address|what is the address to which we transfer the source currency out of the system|
|edge_to_enter|in source currency|
|edge_to_leave|in source currency. edge_to_leave < edge_to_enter|
|period|period in seconds at which the trader runs its loop of checking status, optimizing, making trades, updating quotes|

#### webserver

How to configure the web interface

|Key|Description|
|---|-----------|
|ssl|true/false, whether or not to use SSL. If SSL is enabled, we have to configure keys and certs|
|port|Which port to run on|
|ssl_key|Path to the SSL private key|
|ssl_cert|Path to the SSL cert|
|ssl_cert_chain|Path to the SSL certificate chain|

#### users

users who have access to the web interface

Keys are usernames, values are their passwords, in cleartext

BE SURE TO EDIT THE SAMPLE CONFIG AND REMOVE THE DEFAULT `admin` USER

### Running

```
python ilp.py --config ilp.ini
```

### Management

Connect to the webserver host/port specified in the `webserver` portion of the configuration file.

When the ILP is fully initialized, the trader page will say "READY".

When "READY" the optimizer will run every period, so the operator can check the "Optimized" page to
see the results, modify parameters and see the consequences of changing parameters without any
trades being placed. After changing parameters, click the 'UPDATE' button at the top to push them
to the ILP.

Click "START" to start trading. Trader page will say "TRADING". Quotes will be placed, transfers will be executed.

Click "STOP" to stop trading. Trader page will say "READY". The optimizer will continue running.


## General Client Interface

The clients to each different exchange expose the same API. They return Twisted `Deferred` objects. 

Some APIs don't support certain calls. In those cases they will raise `NotImplementedError`

In order to support the ILP, the exchange client must expose all these API calls. In the case
of deposit and withdrawal functions, the ILP handles `NotImplementedError` and pushes
the requested deposit/withdrawal up for manual intervention.

In these calls values are passed and returned as `Decimal`, not as integers like in the Sputnik API on the wire.

### Constructor

```python
exchange = Exchange(id="client_id", secret="client_secret", endpoint="https://endpoint.com/v1")
```

### Connect

```python
exchange.connect()
```

### getPositions

```python
exchange.getPositions()
```

returns a ticker-indexed dict of positions, just like the API rpc call `rpc.trader.get_positions`

### getCurrentAddress

```python
exchange.getCurrentAddress(ticker)
```

returns a the current cryptocurrency or other form of deposit address for the ticker

### getNewAddress

```python
exchange.getNewAddress(ticker)
```

returns a new cryptocurrency or other form of deposit address for the ticker

### requestWithdrawal

```python
exchange.requestWithdrawal(ticker, amount, address)
```

Request a withdrawal of `amount` of `ticker` to be sent to `address`

### placeOrder

```python
exchange.placeOrder(ticker, quantity, price, side)
```

Place a limit order. Side can be "BUY" or "SELL"

Returns the order id

### cancelOrder

```python
exchange.cancelOrder(id)
```

Cancel an order by order id

### getOpenOrders

```python
exchange.getOpenOrders()
```

Returns all open orders for the user. id-indexed dict of the `order` objects
like in the wire API.

### getOrderBook

```python
exchange.getOrderBook(ticker)
```

Returns the orderbook for the `ticker`

### getTransactionHistory

```python
exchange.getTransactionHistory(start_datetime, end_datetime)
```

`start_datetime` and `end_datetime` are python `datetime` objects.

Returns the user's transaction history between the specified times. Array
of `transaction` objects.


### Events

When things happen, the class emits an event. Events can be handled with 

```python
exchange.on(self, "event_name", handler)
```

The handler is a function that takes as arguments all the arguments that are passed to that event.

#### connect

When the exchange gets connected, this event is called with the exchange class as the only argument

#### disconnect

When the exchange gets disconnected, this event is called with the exchange class as the only argument
