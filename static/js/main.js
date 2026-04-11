function dload() {
	var l = document.createElement("a");
	l.href =
		"data:text/plain;charset=UTF-8," +
		document.getElementById("transcript").value;
	l.setAttribute("download", "transcript.txt");
	l.click();
}
