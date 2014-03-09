events = require "eventemitter2"

class EventEmitter extends events.EventEmitter2
    constructor: ->
        events.EventEmitter2.call @, wildcard: true

module.exports =
    EventEmitter: EventEmitter

