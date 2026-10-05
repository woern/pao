// Team import: a chosen file is read into the textarea so the same form
// handles both a file and pasted text. No upload parsing on the server.
(function () {
  var file = document.getElementById("teamfile");
  var text = document.getElementById("teamtext");
  if (file && text) {
    file.addEventListener("change", function () {
      if (!file.files.length) return;
      var reader = new FileReader();
      reader.onload = function () { text.value = reader.result.replace(/^﻿/, ""); };
      reader.readAsText(file.files[0]);
    });
  }
})();

// Score entry: each game saves itself when either score changes.
(function () {
  var form = document.getElementById("scores");
  if (!form) return;

  var MAX = 13;

  function valid(input) {
    if (input.value === "") return true;
    var n = Number(input.value);
    return Number.isInteger(n) && n >= 0 && n <= MAX;
  }

  function save(row) {
    var inputs = row.querySelectorAll("input.score");
    for (var i = 0; i < inputs.length; i++) {
      if (!valid(inputs[i])) {
        row.className = "game tied";
        row.querySelector(".status").textContent = "scores are 0 to " + MAX + " - not saved";
        inputs[i].focus();
        inputs[i].select();
        return;
      }
    }
    var a = inputs[0].value, b = inputs[1].value;
    row.className = "game saving";
    fetch("/api/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ round: parseInt(inputs[0].dataset.round, 10),
                             tid: parseInt(row.dataset.tid, 10), oid: parseInt(row.dataset.oid, 10),
                             a: a === "" ? null : a, b: b === "" ? null : b })
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (data.error) {
        row.className = "game tied";
        row.querySelector(".status").textContent = data.error;
        return;
      }
      row.className = "game " + data.status;
      row.querySelector(".status").textContent = data.status;
      var s = data.summary;
      var summary = document.getElementById("summary");
      if (summary) summary.textContent = s.ok + " of " + s.games + " games scored, " + s.tied + " tied";
    }).catch(function () {
      row.className = "game partial";
      row.querySelector(".status").textContent = "not saved - check the connection";
    });
  }

  form.addEventListener("change", function (e) {
    if (e.target.classList.contains("score")) save(e.target.closest("tr"));
  });
  // Only digits can be typed into a score box, and never more than two.
  form.addEventListener("input", function (e) {
    if (!e.target.classList.contains("score")) return;
    var cleaned = e.target.value.replace(/[^0-9]/g, "").slice(0, 2);
    if (cleaned !== e.target.value) e.target.value = cleaned;
  });
  // Enter moves to the next box instead of submitting the whole form.
  form.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && e.target.classList.contains("score")) {
      e.preventDefault();
      if (!valid(e.target)) { save(e.target.closest("tr")); return; }
      var boxes = Array.prototype.slice.call(form.querySelectorAll("input.score"));
      var next = boxes[boxes.indexOf(e.target) + 1];
      if (next) { next.focus(); next.select(); }
    }
  });
})();

// Bracket score entry: a match saves itself once both boxes are filled.
(function () {
  var forms = document.querySelectorAll("form.mform");
  if (!forms.length) return;
  Array.prototype.forEach.call(forms, function (form) {
    form.addEventListener("input", function (e) {
      if (!e.target.classList.contains("bscore")) return;
      var cleaned = e.target.value.replace(/[^0-9]/g, "").slice(0, 2);
      if (cleaned !== e.target.value) e.target.value = cleaned;
    });
    form.addEventListener("change", function () {
      var boxes = form.querySelectorAll("input.bscore");
      var a = boxes[0].value, b = boxes[1].value;
      if (a === "" || b === "") return;
      if (Number(a) > 13 || Number(b) > 13 || a === b) {
        form.closest(".match").style.borderColor = "#cf222e";
        return;
      }
      form.submit();
    });
  });
})();
