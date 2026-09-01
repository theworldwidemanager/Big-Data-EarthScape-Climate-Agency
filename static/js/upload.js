// static/js/upload.js
document.getElementById("uploadForm").addEventListener("submit", async function (e) {
  e.preventDefault();

  const fileInput = document.getElementById("fileInput");
  const alertBox = document.getElementById("alertBox");
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  const response = await fetch("/admin/upload", {
    method: "POST",
    body: formData,
  });

  const result = await response.json();

  alertBox.classList.remove("d-none", "alert-success", "alert-danger");
  if (result.success) {
    alertBox.classList.add("alert-success");
    alertBox.innerText = "✅ Data uploaded successfully!";
  } else {
    alertBox.classList.add("alert-danger");
    alertBox.innerText = "❌ " + result.message;
  }
});
