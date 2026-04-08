import os
import csv
import io
import boto3
from PIL import Image
from pillow_heif import register_heif_opener
from flask import Flask, request, jsonify, render_template, send_file
from dotenv import load_dotenv
 
# Register HEIF/HEIC support
register_heif_opener()
 
load_dotenv()
 
app = Flask(__name__)
 
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")
BUCKET_NAME           = os.getenv("S3_BUCKET_NAME")
CSV_KEY               = "atrex_import.csv"
 
 
def get_s3():
    return boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )
 
 
def read_csv_from_s3():
    s3 = get_s3()
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key=CSV_KEY)
        content = obj["Body"].read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        return [{"sku": row["SKU"], "url": row["IMG"]} for row in reader]
    except Exception:
        return []
 
 
def write_csv_to_s3(rows):
    s3 = get_s3()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["SKU", "IMG"])
    for row in rows:
        writer.writerow([row["sku"], row["url"]])
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=CSV_KEY,
        Body=output.getvalue().encode("utf-8"),
        ContentType="text/csv",
    )
 
 
def append_to_s3_csv(new_rows):
    existing = read_csv_from_s3()
    existing.extend(new_rows)
    write_csv_to_s3(existing)
 
 
def convert_to_jpeg(file_obj):
    raw = file_obj.read()
    if not raw:
        raise ValueError("Empty file received")
    img = Image.open(io.BytesIO(raw))
    img = img.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    buffer.seek(0)
    return buffer
 
 
def upload_image_to_s3(file_obj, filename):
    s3 = get_s3()
    filename = filename or "image.jpg"
    base = os.path.splitext(os.path.basename(filename))[0] or "image"
    safe_filename = f"{base}.jpg"
    jpeg_buffer = convert_to_jpeg(file_obj)
    s3.upload_fileobj(
        jpeg_buffer,
        BUCKET_NAME,
        safe_filename,
        ExtraArgs={"ContentType": "image/jpeg"},
    )
    return f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{safe_filename}"
 
 
@app.route("/")
def index():
    return render_template("index.html")
 
 
@app.route("/logo")
def logo():
    logo_path = os.path.join(os.path.dirname(__file__), "logo.jpeg")
    return send_file(logo_path, mimetype="image/jpeg")
 
 
@app.route("/records")
def records():
    return jsonify(read_csv_from_s3())
 
 
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
            url = upload_image_to_s3(file, filename)
            results.append({"sku": sku, "url": url})
        except Exception as e:
            errors.append(f"{filename}: {str(e)}")
 
    if results:
        append_to_s3_csv(results)
 
    return jsonify({
        "uploaded": results,
        "errors": errors,
    })
 
 
@app.route("/download")
def download():
    rows = read_csv_from_s3()
    if not rows:
        return jsonify({"error": "No data yet"}), 404
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["SKU", "IMG"])
    for row in rows:
        writer.writerow([row["sku"], row["url"]])
    buffer = io.BytesIO(output.getvalue().encode("utf-8"))
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="atrex_import.csv", mimetype="text/csv")
 
 
@app.route("/clear", methods=["POST"])
def clear():
    s3 = get_s3()
    try:
        s3.delete_object(Bucket=BUCKET_NAME, Key=CSV_KEY)
    except Exception:
        pass
    return jsonify({"message": "CSV cleared"})
 
 
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
 
