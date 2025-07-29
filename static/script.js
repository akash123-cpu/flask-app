$(document).ready(function() {
    $("#databaseSelect").change(function() {
        let selectedDB = $(this).val();
        if (selectedDB) {
            $.ajax({
                url: "/get_tables",
                type: "POST",
                contentType: "application/json",
                data: JSON.stringify({ database_name: selectedDB }),
                success: function(tables) {
                    $("#tableSelect").empty().append('<option value="">-- Choose Table --</option>');
                    tables.forEach(table => {
                        $("#tableSelect").append(`<option value="${table}">${table}</option>`);
                    });
                    $("#tableSelect, #viewDataBtn").removeClass("hidden");
                }
            });
        }
    });

    $("#viewDataBtn").click(function() {
        let database = $("#databaseSelect").val();
        let table = $("#tableSelect").val();
        if (database && table) {
            window.location.href = `/view_data/${database}/${table}`;
        } else {
            alert("Please select both a database and a table.");
        }
    });
});
