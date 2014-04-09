jQuery.fn.serializeObject = ->
    arrayData = @serializeArray()
    objectData = {}
    $.each arrayData, ->
        if @value?
            value = @value
        else
            value = ''
        if objectData[@name]?
            unless objectData[@name].push
                objectData[@name] = [objectData[@name]]
            objectData[@name].push value
        else
            objectData[@name] = value
    return objectData

@compliance_client_handler = (form) ->
    sputnik.getRequestSupportNonce 'Compliance', (nonce) ->
      fd = new FormData()
      fd.append('username', $("#login_name").text())
      fd.append('nonce', nonce)
      fd.append('file', form.find('input[name=file]')[0].files[0])
      fd.append('file', form.find('input[name=file]')[1].files[0])
      fd.append('data', JSON.stringify(form.serializeObject()))
      $.ajax
        url: "#{location.protocol}//#{location.hostname}:8980/create_kyc_ticket",
        data: fd,
        processData: false,
        contentType: false,
        type: 'POST',
        success: (data) ->
            alert("Successfully saved:" + data)
        error: (err) ->
            alert("Error while saving:" + err)
            sputnik.log "Error:", err


