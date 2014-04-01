@compliance_client_handler = (form) ->
  console.log "[mexbt:2 - form]", form
  fd = new FormData(form)
  $.ajax
    url: 'script.php',
    data: fd,
    processData: false,
    contentType: false,
    type: 'POST',
    success: (data) -> alert(data)

$ ->
  $('#chatBox').keypress (e)-> $('#chatButton').click() if e.keyCode == 13