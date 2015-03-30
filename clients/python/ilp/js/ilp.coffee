$ ->
    $.ajax {
        url: "template.html"
        success: (data, status, xhr) ->
           start(data)
    }

    error_handler = (xhr, textStatus, errorThrown) ->
        alert "#{textStatus}: #{errorThrown}"

    start = (template) ->
        $.ajax {
            url: "api/update"
            dataType: "json"
            error: error_handler
            success: (data, status, xhr) ->
                data.format_timestamp = (timestamp) ->
                    d = new Date(timestamp/1e3)
                    d.toLocaleTimeString()

                data.timestamp = Date.now() * 1e3

                ractive = new Ractive
                    el: "target"
                    template: template
                    data: data

                paused = false

                update_success = (data, status, xhr) ->
                    ractive.set data
                    ractive.set "timestamp", Date.now()*1e3
                    paused = false

                ractive.on
                    start: (event) ->
                        event.original.preventDefault()
                        $.ajax {
                            url: "api/start"
                            error: error_handler
                            success: update_success
                        }
                    stop: (event) ->
                        event.original.preventDefault()
                        $.ajax {
                            url: "api/stop"
                            error: error_handler
                            success: update_success
                        }
                    post: (event) ->
                        $.ajax {
                            type: "POST"
                            url: "api/update"
                            data: JSON.stringify(ractive.get())
                            contentType: "application/json"
                            dataType: "json"
                            error: error_handler
                            success: update_success
                        }
                    pause: (event) ->
                        event.original.preventDefault()
                        paused = true

                update = () ->
                    if not paused
                        $.ajax {
                            url: "api/update"
                            dataType: "json"
                            error: error_handler
                            success: update_success
                        }

                setInterval(update, 1000)
        }





