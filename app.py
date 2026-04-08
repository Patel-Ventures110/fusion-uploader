import os
import csv
import io
import boto3
from PIL import Image
from flask import Flask, request, jsonify, render_template, send_file
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")
BUCKET_NAME           = os.getenv("S3_BUCKET_NAME")
CSV_FILE              = "atrex_import.csv"


def convert_to_jpeg(file_obj):
    """Convert any image to JPEG format and return as bytes buffer."""
    img = Image.open(file_obj)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    buffer.seek(0)
    return buffer


def upload_to_s3(file_obj, filename):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )

    # Convert to JPEG and rename extension
    jpeg_buffer = convert_to_jpeg(file_obj)
    base = os.path.splitext(os.path.basename(filename))[0]
    safe_filename = f"{base}.jpg"

    s3.upload_fileobj(
        jpeg_buffer,
        BUCKET_NAME,
        safe_filename,
        ExtraArgs={"ContentType": "image/jpeg"},
    )
    return f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{safe_filename}"


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
    logo_path = os.path.join(os.path.dirname(__file__), "logo.jpeg")
    return send_file(logo_path, mimetype="image/jpeg")


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
            filename = file.filename or "image.jpg"
            url = upload_to_s3(file, filename)
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
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
