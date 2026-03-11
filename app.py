import os
import csv
import mimetypes
import boto3
from flask import Flask, request, jsonify, render_template, send_file
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")
BUCKET_NAME           = os.getenv("S3_BUCKET_NAME")
CSV_FILE              = "atrex_import.csv"


def upload_to_s3(file_obj, filename):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )
    content_type, _ = mimetypes.guess_type(filename)
    if not content_type:
        content_type = "image/jpeg"

    s3.upload_fileobj(
        file_obj,
        BUCKET_NAME,
        filename,
        ExtraArgs={"ContentType": content_type},
    )
    return f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{filename}"


def append_to_csv(rows):
    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["SKU", "IMG"])
        for row in rows:
            writer.writerow(row)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/logo")
def logo():
    return send_file("logo.jpeg", mimetype="image/jpeg")


@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("images")
    skus  = request.form.getlist("skus")

    if not files or not skus or len(files) != len(skus):
        return jsonify({"error": "Mismatched images and SKUs"}), 400

    results = []
    errors  = []

    for file, sku in zip(files, skus):
        sku = sku.strip().upper()
        if not sku:
            errors.append(f"{file.filename}: SKU is empty")
            continue
        try:
            url = upload_to_s3(file, file.filename)
            results.append((sku, url))
        except Exception as e:
            errors.append(f"{file.filename}: {str(e)}")

    if results:
        append_to_csv(results)

    return jsonify({
        "uploaded": [{"sku": r[0], "url": r[1]} for r in results],
        "errors": errors,
    })


@app.route("/download")
def download():
    if not os.path.exists(CSV_FILE):
        return jsonify({"error": "No CSV file yet"}), 404
    return send_file(CSV_FILE, as_attachment=True, download_name="atrex_import.csv")


@app.route("/clear", methods=["POST"])
def clear():
    if os.path.exists(CSV_FILE):
        os.remove(CSV_FILE)
    return jsonify({"message": "CSV cleared"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
