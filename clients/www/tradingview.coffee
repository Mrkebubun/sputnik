#!/usr/bin/env python
#
# Copyright 2014 Mimetic Markets, Inc.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
if module?
    global.window = require "./window.js"

### TradingView API ###

class @TVFeed
    subscribed: {}
    quotes: {}
    info: {}
    markets: {}

    constructor: (@sputnik) ->
        # Trading View API

    setup: (reserved, callback) =>
        @sputnik.log "setup called"
        @sputnik.call("rpc.info.get_exchange_info").then (@info) =>
            config_data = {
                exchanges: [ @info.name ]
                symbols_types: [ 'cash_pair', 'futures', 'prediction' ]
                supported_resolutions: ["1", "60", 'D']
                supports_marks: false
            }
            @sputnik.log ["callback", config_data]
            callback(config_data)

    searchSymbolsByName: (userInput, exchange, symbolType, onResultReadyCallback) =>
        @sputnik.log ["searchSymbolsByName", userInput, exchange, symbolType]
        @sputnik.call("rpc.market.get_markets").then (markets) =>
            return_array = []
            for ticker, details of markets
                if details.contract_type != "cash"
                    if symbolType == "" or details.contract_type == symbolType
                        if userInput == "" or ticker.indexOf(userInput) > -1
                            return_array.push {
                                    symbol: ticker,
                                    full_name: details.description,
                                    exchange: @info.name,
                                    ticker: ticker,
                                    type: details.contract_type
                            }

            @sputnik.log ["onResultReadyCallback", return_array]
            onResultReadyCallback return_array

    resolveSymbol: (symbolName, onSymbolResolvedCallback, onResolveErrorCallback) =>
        @sputnik.log ["resolveSymbol", symbolName]
        @sputnik.call("rpc.market.get_markets").then (markets) =>
            if symbolName of markets
                info = {
                    name: symbolName
                    "exchange-traded": @info.name
                    "exchange-listed": @info.name
                    timezone: 'Europe/London',
                    pricescale: @sputnik.getPriceScale(symbolName)/@sputnik.getMinMove(symbolName)
                    minmove: 1
                    has_intraday: true
                    intraday_multipliers: [1]
                    has_daily: true
                    has_weekly_and_monthly: false
                    has_empty_bars: false
                    force_session_rebuild: false
                    has_no_volume: false
                    volume_precision: @sputnik.getQuantityPrecision(symbolName)
                    has_fractional_volume: true
                    ticker: symbolName
                    description: markets[symbolName].description
                    session: "24x7"
                    data_status: 'REALTIME'
                    supported_resolutions: ["1", "60", 'D']
                    type: markets[symbolName].contract_type
                }
                @sputnik.log ["onSymbolResolvedCallback", info]
                onSymbolResolvedCallback info


    getBars: (symbolInfo, resolution, from, to, onHistoryCallback, onErrorCallBack) =>
        @sputnik.log ["getBars", symbolInfo, resolution, from, to]
        from_timestamp = from * 1e6
        to_timestamp = to * 1e6
        if resolution == "1"
            period = "minute"
        else if resolution == "60"
            period = "hour"
        else if resolution == "D"
            period = "day"

        @sputnik.call("rpc.market.get_ohlcv_history", symbolInfo.name, period, from_timestamp, to_timestamp).then (history) =>
            return_bars = []
            for timestamp, bar of history
                return_bars.push {
                    time: timestamp / 1000
                    open: @sputnik.priceFromWire(symbolInfo.name, bar.open)
                    close: @sputnik.priceFromWire(symbolInfo.name, bar.close)
                    high: @sputnik.priceFromWire(symbolInfo.name, bar.high)
                    low: @sputnik.priceFromWire(symbolInfo.name, bar.low)
                    volume: @sputnik.quantityFromWire(symbolInfo.name, bar.volume)
                }
            return_bars.sort (a, b) -> a.time - b.time
            @sputnik.log ["onHistoryCallback", return_bars]
            onHistoryCallback return_bars
        , (error) =>
            @sputnik.log ["onErrorCallback", error]
            onErrorCallBack error

    subscribeBars: (symbolInfo, resolution, onRealtimeCallback, subscriberUID) =>
        @sputnik.log ["subscribeBars", symbolInfo, resolution, subscriberUID]
        if resolution == 1
            period = "minute"
        else if resolution == 60
            period = "hour"
        else if resolution == "D"
            period = "day"

        encoded_market = @sputnik.encode_market(symbolInfo.name)
        @sputnik.subscribe "feeds.market.ohlcv.#{encoded_market}", (bar) =>
            if bar.period == period
                return_bar = {
                    time: ohlcv.timestamp / 1e3
                    open: @sputnik.priceFromWire(symbolInfo.name, bar.open)
                    close: @sputnik.priceFromWire(symbolInfo.name, bar.close)
                    high: @sputnik.priceFromWire(symbolInfo.name, bar.high)
                    low: @sputnik.priceFromWire(symbolInfo.name, bar.low)
                    volume: @sputnik.quantityFromWire(symbolInfo.name, bar.volume)
                }
                @sputnik.log ["onRealtimeCallback", return_bar]
                onRealtimeCallback return_bar
        if subscriberUID in @subscribed
            @subscribed[subscriberUID].push symbolInfo.name
        else
            @subscribed[subscriberUID] = [symbolInfo.name]

    unsubscribeBars: (subscriberUID) =>
        @sputnik.log ["unsubscribeBars", subscriberUID]
        if subscriberUID in @subscribed
            for symbol in @subscribed[subscriberUID]
                encoded_market = @sputnik.encode_market(symbol)
                @sputnik.unsubscribe "feeds.market.ohlcv.#{encoded_market}"
                delete @subscribed[subscriberUID]

    getQuotes: (symbols, onDataCallback, onErrorCallback) =>
        @sputnik.log ["getQuotes", symbols]
        dlist = []
        for symbol in symbols
            dlist.push @sputnik.call("rpc.market.get_order_book", symbol)

        $.when(dlist).then (results) =>
            @sputnik.log ["onDataCallback", results]
            onDataCallback(results)

    subscribeQuotes: (symbols, fastSymbols, onRealtimeCallback, subscriberUID) =>
        @sputnik.log ["subscribeQuotes", symbols, fastSymbols, subscriberUID]
        for symbol in symbols + fastSymbols
            encoded_symbol = @sputnik.encode_market symbol
            @sputnik.subscribe("feeds.market.book.#{encoded_symbol}").then (book) =>
                @sputnik.log ["onRealtimeCallback", book]
                onRealtimeCallback book

        if subscriberUID in @quotes
            @quotes[subscriberUID].push.apply @quotes[subscriberUID], symbols + fastSymbols
        else
            @quotes[subscriberUID] = symbols + fastSymbols

    unsubscribeQuotes: (subscriberUID) =>
        @sputnik.log ["unsubscribeQuotes", subscriberUID]
        for symbol in @quotes[subscriberUID]
            encoded_symbol = @sputnik.encode_market symbol
            @sputnik.unsubscribe("feeds.market.book.#{encoded_symbol}")

        delete @quotes[subscriberUID]














