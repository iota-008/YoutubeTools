function fnc() {
	url = Flask.url_for("static", { filename: "data.txt" });
	// url = "../static/data.txt"; this also works
	var myHeaders = new Headers();
	myHeaders.append("pragma", "no-cache");
	myHeaders.append("cache-control", "no-cache");

	var myInit = {
		method: "GET",
		headers: myHeaders,
	};

	fetch(url, myInit)
		.then(function (response) {
			console.log(response);
			return response.text();
		})
		.then(function (data) {
			console.log(data);
			document.getElementById("transcript").innerText = data;
		});
}

function dload() {
	var l = document.createElement("a");
	l.href =
		"data:text/plain;charset=UTF-8," +
		document.getElementById("transcript").value;
	l.setAttribute("download", "transcript.txt");
	l.click();
}

function downloadThumbnail(url, name = "thumbnail") {
	const proxyurl = "https://cors-anywhere.herokuapp.com/";
	let headers = new Headers();
	headers.append("Access-Control-Allow-Origin", "http://127.0.0.1:5000");
	headers.append("Access-Control-Allow-Credentials", "true");

	axios(
		{
			url: proxyurl + url,
			method: "GET",
			responseType: "blob",
		},
		headers
	)
		.then((response) => {
			const url = window.URL.createObjectURL(new Blob([response.data]));
			const link = document.createElement("a");
			link.href = link;
			link.setAttribute("download", "Thumbnail.jpg");
			document.body.appendChild(link);
			link.click();
		})
		.catch(() =>
			console.log("Can’t access " + url + " response. Blocked by browser?")
		);
}
