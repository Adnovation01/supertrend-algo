$(document).ready(function () {

    function toggleVisibility(field) {
        var fieldType = field.attr('type');
        if (fieldType === 'password') {
            field.attr('type', 'text');
            $('#togglePassword').removeClass('fa-eye').addClass('fa-eye-slash');
        } else {
            field.attr('type', 'password');
            $('#togglePassword').removeClass('fa-eye-slash').addClass('fa-eye');
        }
    }

    $('#togglePassword').on('click', function () {
        var accessTokenField = $('#access_token');
        toggleVisibility(accessTokenField);
    });

});
