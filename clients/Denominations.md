# Denominations

Denominations refers to granularity imposed on orders to ensure they are reasonable, conversion between different units, and payouts for contracts.

When placing an order, the user fills two boxes, giving us two variables
* quantity_entered
* price_entered

These values correspond to human meaningful numbers and do *not* directly map to price and quantity in the order object as processed by the exchange. The conversion between human units and exchange units depends on the type of contract and is described below.

# Fixed point conversion

Prices and quantities must be integers to avoid rounding errors. For this reason, the exchange stores all balances as integers. Unfortunately, human readable units usually require floating point numbers. For example, it is inconvenient to talk about 123 USD cents. It is much easier to talk about 1.23 USD.

The exchange keeps track of user cash positions to a fixed precision. The exact precision is stored in the denominator for the cash contract and depends on the currency. The denominator is also the conversion factor between human readable units and exchange accounting units. For example, 1 BTC is 1e8 satoshi. The exchange keeps track of each users' satoshi balance, however the human readable unit is BTC. So, the conversion factor is 1e8.

| |  denominator | human readable unit |  exchange accounting unit           |
|-------------|---------------------|--------------------------|-------------|
| BTC         | 1e8                 | bitcoin                  | satoshi     |
| USD         | 1e2                 | dollar                   | dollar cent |
| EUR         | 1e2                 | euro                     | euro cent   |
| MXN         | 1e2                 | peso                     | peso cent   |

# Cash

Cash contracts are basic currencies that a user can deposit/withdraw from the system. As noted above, the denominator defines the exact
precision for which a cash contract is stored. The exchange may store internally a cash contract to more units of precision
than the exchange may wish to allow deposits/withdrawals. For this difference we use the lot_size to define the minimum
unit for which deposits/withdrawals are permitted.


# Cash pairs

When a user trades between two currencies, there is a third contract involved. It is a called a "cash pair" and it always has the format `to_currency/from_currency`. For example, if a user wishes to purchase bitcoins in exchange for pesos, they would place an order on the BTC/MXN contract.

The cash pair has three fields, a tick size, lot size, and a denominator. All prices must be multiples of tick size. All quantities must be multiples of lot size. The denominator has a special meaning and will be discussed later.

Here is a simple example:

|             | denominator | tick size | lot size |
|-------------|-----------|----------|-----|
| BTC         | 1e8       | n/a      | n/a |
| MXN         | 1e2       | n/a      | n/a |
| BTC/MXN     | 1         | 1e2      | 1e6 |


Suppose the user wishes to place an order

* 0.975 BTC at
* 10350.213 pesos per BTC

The user's client prepares the order by converting it to proper units.

1. The quantity is converted into exchange units by multiplying by the denominator of the to_currency.
```
    0.975 * 1e8 = 97,500,000
```

2. The quantity is coerced into a multiple of the lot size. This also makes sure that quantity is an integer.
```
    round(97,500,000 / 1e6) * 1e6 = 97,000,000
```

3. The price is converted into exchange units by multiplying by the denominator of the the from_currency.
```
    10,350.21 * 1e2 = 1,035,021.3
```

4. The price is coerced into a multiple of the tick size. This also makes sure that price is an integer.
```
    round(1,035,021.3 / 1e2) * 1e2 = 1,035,000
```

*Note:* The result from step 2 should match the result from step 1 and the result from step 4 should match the result from step 3. If it does not, the user entered too much precision. For example, in this case, 1e6 satoshi corresponds to 0.01 BTC. Since the user entered 0.975, the value was rounded down. The user's client should catch this and alert them, or prevent them from entering the value in the first place.

The actual order that is placed is
* 97,500,000 satoshi at
* 1035000 peso cents per BTC

*Note:* The price is peso cents per bitcoin. It is *not* peso cents per satoshi.

# Cash pairs (advanced)

The problem with the example above is the granularity of the orders placed is determined by the accounting units used by the exchange. This is undesirable in some cases. For example, both euros and dollars have a currency denominator of 1e2. This means it is normally impossible to place an order with a price specified to 3 decimal places. The cash pair denominator modifies the order so that the price is for a denominator worth of the target currency.

Here is a more complicated example:

| | denominator | tick size | lot size |
|-------------|-----------|----------|-----|
| USD         | 1e2       | n/a      | n/a |
| EUR         | 1e2       | n/a      | n/a |
| EUR/USD     | 1         | 1        | 1e2 |

Suppose the user wishes to place an order

* 1 euro at
* 1.01 dollar per euro

As detailed in the previous example, this order gets converted to the actual order of
* 100 euro cents at
* 101 dollar cents per euro

When the order fills, the user's balance changes by 100 euro cents and 101 dollar cents.

Now suppose the user wants to place an order with the price 1.001 dollars per euro. This is not possible. The net effect would be that the change in the users USD position is by 100.1 cents. Since the exchange does not keep track of fractions of a cent, this order would be rejected. At the same time, it is useful to allow such orders. So, the cash pair denominator is introduced.

We still cannot allow the user to purchase 1 euro at a price of 1.001 dollars per euro. However, if the user agrees to purchase 10 euros at a time, this price is allowable. Consider the following table:

| | denominator | tick size | lot size |
|-------------|-----------|----------|-----|
| USD         | 1e2       | n/a      | n/a |
| EUR         | 1e2       | n/a      | n/a |
| EUR/USD     | 10        | 1        | 1e3 |

The cash pair denominator is 10. This means when the price is transmitted to the server, it will be the price for 10 euros. The only difference to the user is they get an additional digit for the price and they must purchase multiples of 10 euros (this is reflected in the lot size). The user may now place their order at the desired price.

The user places an order for
* 10 euros at
* 1.001 dollars per euro

The user's client prepares the order by converting it to proper units.

1. The quantity is converted into exchange units by multiplying by the denominator of the to_currency.
```
    10 * 1e2 = 1000
```

2. The quantity is coerced into a multiple of the lot size. This also makes sure that quantity is an integer.
```
    round(1000 / 1e3) * 1e3 = 1000
```

3. The price is converted into exchange units by multiplying by the denominator of the the from_currency.
```
    1.001 * 1e2 = 100.1
```

4. Now the price is multiplied by the cash pair denominator.
```
    100.1 * 10 = 1001
```

5. The price is coerced into a multiple of the tick size. This also makes sure that price is an integer.
```
    round(1001 / 1) * 1 = 1001
```

The actual order that is placed is
* 1000 euro cents at
* 1001 dollar cents per 10 euros

This order is transmitted to the webserver, which reject it if it does not match the given tick/lot sizes. It then passes the order to the accountant. The affect on the user's position is calculated as follows.

```
    euro cent delta = quantity = 1000
    dollar cent delta = quantity * price / (to_currency.denominator * cash_pair.denominator) = 1000 * 1001 / (100 * 10) = 1001
```

# Predictions

Predictions only have two contracts involved, the denomination contract (usually BTC) and the prediction contract itself. 
The fields are very similar with cash, except that denominator is always 1.

| | denominator | tick size | lot size |
|-------------|-----------|----------|-----|
| BTC         | 1e8       | n/a      | n/a |
| US_PRESIDENT    | 1e3        | 1        | 1e5 |

* Denominator tells us that the price can go from 0 to 1000, which means that when the probability is 1, the price is 1000.
* Tick size tells us the granularity of allowed price changes. There's no reason this should be anything other than 1
* the lot size is the number of BTC (satoshi in this case, because BTC.denominator = 1e8) that is represented by one contract

contract.lot_size * contract.tick_size / contract.denominator must be an integer

Note that in cash_pair, the price is the price in from_currency, per 'contract.denominator' of to_currency. However, 
in prediction markets, the price is in probability space, it doesn't reflect an actual currency value.

You can only buy integer qty of contracts. You can't buy/sell a fractional contract.

Price must be an integer between 0 and denominator


## Cost calculations

When someone purchases a single contract for 0.454 (454 if the denominator is 1000) then the amount spent (in satoshi,
because BTC.denominator is 1e8) is

```
    price * contract.lot_size / contract.denominator = 454 * 1e5 / 1e3
```

If they purchase two contracts, the amount spent is twice that:

```
    quantity * price * contract.lot_size / contract.denominator = 2 * 454 * 1e5 / 1e3
```
# Futures

Futures only have two contracts involved, the denomination contract (usually BTC) and the futures contract itself. 

| | denominator | tick size | lot size |
|-------------|-----------|----------|-----|
| BTC         | 1e8       | n/a      | n/a |
| USDBTC      | 1e4       | 1        | 1e5 |
| RAINFALL    | 1e2       | 1        | 1e5 |
| IPO         | 1e3       | 1e1      | 1e5 |

Every contract's price is an index value which is defined in the contract description, which determines the settlement price
at expiry.

For example, for a USDBTC future, the index value may be the reciprocal out to four decimal places
of the Bitstamp BTC/USD price at
a specified time. (Which is the price of a single dollar in bitcoin.) For a rain future, the index value might
be the total number of centimeters of rain in a given month, out to two decimal places. For an IPO future,
the index value might be the market capitalization of the company 180 days after the IPO, in billions of dollars.

The lot size defines how many Bitcoin (satoshi) is associated with each index point.
  
The denominator tell us how the price is represented internally as an integer.

The tick size tells us the minimum price movement when trading. 

Internal price:

```
index_value * denominator
```

Value per tick:
```
lot_size * tick_size / denominator
```

Tick size in terms of index value
```
tick_size / denominator (index units)
```

| contract | price | internal price | value per tick (satoshi) | tick_size in terms of index value |
|----------|-------------|------------------|
| USDBTC   | 0.0025 USD/BTC | 25 | 1e2 | 0.0001 USD/BTC |
| RAINFALL | 20.04 cm | 2004 | 1e3 | 0.01 cm |
| IPO | USD 250mm | 250 | 1e3 | USD 10mm |


You can only buy/sell integer qty of contracts. You can't buy/sell a fractional contract.


### Trading

On a trade, if the user already has a position in the contract, the reference price must be updated to the
new trade price. Therefore, in addition to fees, a settlement cashflow takes place based on the pre-existing
position:

```
quantity * (trade_price - reference_price) * lot_size / denominator
```

### Settlement

On settlement, a user's cash flow is calculated:

```
quantity * (settlement_price - reference_price) * lot_size / denominator
```

And their reference_price is reset to their settlement_price.


# Equations

In the following, the & symbol is used:

```
x & y === x - x % y
```
| contract_type 	| price to wire                                                                        	| quantity to wire                                           	| price from wire                                                   	| quantity from wire                     	| cash_spent (using on-wire integer values)                               	|
|---------------	|--------------------------------------------------------------------------------------	|------------------------------------------------------------	|-------------------------------------------------------------------	|----------------------------------------	|-------------------------------------------------------------------------	|
| cash          	| N/A                                                                                  	| quantity * contract.denominator                            	| NA                                                                	| quantity / contract.denominator        	| NA                                                                      	|
| cash_pair     	| price * contract.denominator * denominated_contract.denominator & contract.tick_size 	| quantity * payout_contract.denominator & contract.lot_size 	| price / (contract.denominator * denominated_contract.denominator) 	| quantity / payout_contract.denominator 	| quantity * price / (contract.denominator * payout_contract.denominator) 	|
| prediction    	| price * contract.denominator & contract.tick_size                                    	| quantity & 1                                               	| price / contract.denominator                                      	| quantity                               	| quantity * price * contract.lot_size / contract.denominator             	|
| futures           | price * contract.denominator & contract.tick_size                                     | quantity & 1                                                  | price / contract.denominator                                          | quantity                                  | quantity * (settlement_price - reference_price) * contract.lot_size / contract.denominator |

# Additional notes

Note that we have to be careful to avoid introducing floats into the calculations. Do multiplications before divisions.

It might seem tempting to work on the server size directly with a "number_of_lots" and "price_per_lot_per_tick"
concept, but these would break the history of trades if we were to change tick_size and lot_size, which can happen
in markets.