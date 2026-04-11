function dload() {
	var l = document.createElement("a");
	l.href =
		"data:text/plain;charset=UTF-8," +
		document.getElementById("transcript").value;
	l.setAttribute("download", "transcript.txt");
	l.click();
}

document.addEventListener("DOMContentLoaded", function () {
	var loader = document.getElementById("global-loader");
	var forms = document.querySelectorAll("form[data-loading='true']");

	if (!loader || forms.length === 0) {
		return;
	}

	forms.forEach(function (form) {
		form.addEventListener("submit", function () {
			loader.classList.add("is-visible");
			loader.setAttribute("aria-hidden", "false");

			var submitButtons = form.querySelectorAll(
				"button[type='submit'], input[type='submit']"
			);
			submitButtons.forEach(function (button) {
				button.disabled = true;
			});
		});
	});
});
