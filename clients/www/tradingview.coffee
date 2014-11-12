# Copyright (c) 2014, Mimetic Markets, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

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
        @sputnik.call("get_exchange_info").then (@info) =>
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
        @sputnik.call("get_markets").then (markets) =>
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
        @sputnik.call("get_markets").then (markets) =>
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
                    has_empty_bars: true
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

        @sputnik.call("get_ohlcv_history", symbolInfo.name, period, from_timestamp, to_timestamp).then (history) =>
            return_bars = []
            for timestamp, bar of history
                return_bars.push {
                    time: timestamp / 1e3
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

        @sputnik.subscribe "ohlcv##{symbolInfo.name}", (bar) =>
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
                @sputnik.unsubscribe "ohlcv##{@subscribed[subscriberUID]}"
                delete @subscribed[subscriberUID]

    getQuotes: (symbols, onDataCallback, onErrorCallback) =>
        @sputnik.log ["getQuotes", symbols]
        dlist = []
        for symbol in symbols
            dlist.push @call("get_order_book", symbol)

        $.when(dlist).then (results) =>
            @sputnik.log ["onDataCallback", results]
            onDataCallback(results)

    subscribeQuotes: (symbols, fastSymbols, onRealtimeCallback, subscriberUID) =>
        @sputnik.log ["subscribeQuotes", symbols, fastSymbols, subscriberUID]
        for symbol in symbols + fastSymbols
            @sputnik.subscribe("book##{symbol}").then (book) =>
                @sputnik.log ["onRealtimeCallback", book]
                onRealtimeCallback book

        if subscriberUID in @quotes
            @quotes[subscriberUID].push.apply @quotes[subscriberUID], symbols + fastSymbols
        else
            @quotes[subscriberUID] = symbols + fastSymbols

    unsubscribeQuotes: (subscriberUID) =>
        @sputnik.log ["unsubscribeQuotes", subscriberUID]
        for symbol in @quotes[subscriberUID]
            @sputnik.unsubscribe("book##{symbol}")

        delete @quotes[subscriberUID]














