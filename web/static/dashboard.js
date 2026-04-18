function copyToClipboard(id) {
    var copyText = document.getElementById(id);
    var tempInput = document.createElement("textarea");
    tempInput.value = copyText.value;
    document.body.appendChild(tempInput);
    tempInput.select();
    tempInput.setSelectionRange(0, 99999);
    document.execCommand("copy");
    document.body.removeChild(tempInput);
    alert("Copied: " + copyText.value);
}

function adjustTextareaHeight(id) {
    var textarea = document.getElementById(id);
    textarea.style.height = 'auto';
    textarea.style.height = (textarea.scrollHeight) + 'px';
}

document.addEventListener("DOMContentLoaded", function () {
    adjustTextareaHeight('message-template');
});