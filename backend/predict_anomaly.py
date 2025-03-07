from ultralytics import YOLO
import os
import json
from PIL import Image, ImageDraw, ImageFont
from backend.file_manager import FileManager

# Load the YOLO model
try:
    model = YOLO("./backend/best-40classes.pt")  # Load the YOLO model
    print("Model loaded successfully.")
except Exception as e:
    print(f"Error loading model: {e}")
    exit()

# Directories
JSON_FOLDER = './json_reports'
EXTRACTED_DATA_FOLDER = './extracted_data'
RESULTS_FOLDER = './results'

os.makedirs(RESULTS_FOLDER, exist_ok=True)  # Ensure results directory exists

# Load font
font_path = "/Library/Fonts/Arial.ttf"  # Adjust for OS
font_size = 20
try:
    font = ImageFont.truetype(font_path, font_size)
except Exception as e:
    print(f"Error loading font: {e}. Using default font.")
    font = ImageFont.load_default()

# Initialize FileManager
file_manager = FileManager()


def process_json(file_name):
    """Update JSON with AI Tap Condition, AI Predictions, and Flags."""
    print(f"Processing started for file: {file_name}")
    json_path = os.path.join(JSON_FOLDER, file_name)
    progress_path = os.path.join('./progress', f"{file_name}_progress.json")  # Progress file path

    if not os.path.exists(json_path):
        print(f"JSON file {json_path} does not exist.")
        return

    # Load JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        print(f"Loaded JSON for file: {file_name}")

    taps = data.get('items', {}).get('Taps', [])
    progress = {"status": "in_progress", "rows": []}  # Initialize progress data

    # Map conditions to numeric values
    condition_map = {"Good": 1, "Minor repair": 2, "Major repair": 3, "Reconstruction": 4}

    for index, tap in enumerate(taps):
        # Collect 'Photo' key value along with 'Photo1', 'Photo2', ..., 'Photo5'
        photos = [tap.get('Photo')] + [tap.get(f'Photo{i}') for i in range(1, 6) if tap.get(f'Photo{i}')]
        # Filter out any None values from the list
        photos = [photo for photo in photos if photo]
        
        print(f"Processing tap {index + 1}/{len(taps)}")
        print(f"Collected photos: {photos}")


        if not photos:
            tap['AI Predictions'] = "No image"
            tap['AI Tap Condition'] = "Unknown"
            tap['Flag'] = "transparent"
            print(f"Skipping tap {index + 1}: No images provided.")
            continue

        detected_classes = {cls: False for cls in model.names.values()}  # Aggregate detected classes
        ai_predictions = []

        for photo_path in photos:
            # Resolve and normalize the photo path
            if photo_path.startswith(EXTRACTED_DATA_FOLDER):
                full_photo_path = os.path.normpath(photo_path.replace("extracted_data/extracted_data", "extracted_data"))
            else:
                full_photo_path = os.path.normpath(os.path.join(EXTRACTED_DATA_FOLDER, photo_path))

            if not os.path.exists(full_photo_path):
                print(f"File not found: {full_photo_path}")
                continue

            # Run YOLO model on the image
            try:
                print(f"Running model on {full_photo_path}")
                results = model.predict(full_photo_path, classes=list(range(40)), conf=0.1)

                for result in results:
                    for box in result.boxes:
                        cls_index = int(box.cls)
                        cls_name = model.names[cls_index]
                        detected_classes[cls_name] = True

            except Exception as e:
                print(f"Error processing {full_photo_path}: {e}")

        # Generate AI Predictions based on aggregated results
        if detected_classes["tap"]:
            ai_predictions.append("tap detected")
        else:
            ai_predictions.append("tap not detected")
        if detected_classes["meter"]:
            ai_predictions.append("meter detected")
        else:
            ai_predictions.append("meter not detected")
        if detected_classes["brokenpipe"]:
            ai_predictions.append("brokenpipe")
        if detected_classes["corrosion"]:
            ai_predictions.append("corrosion")
        if detected_classes["concretepost"] or detected_classes["tap_junction"]:
            ai_predictions.append("concrete post detected")
        else:
            ai_predictions.append("concrete post not detected")
        if (
            detected_classes["platform_with_objects"]
            or detected_classes["platformboundary"]
            or detected_classes["platform_notseenfull"]
            or detected_classes["platform_notseenfull_with_objects"]
            or detected_classes["cemented_floor"]
        ):
            ai_predictions.append("platform detected")
        else:
            ai_predictions.append("platform not detected")

        tap["AI Predictions"] = "\n".join(ai_predictions)
        print(f"AI Predictions for tap {index + 1}: {tap['AI Predictions']}")

        # Determine AI Tap Condition
        tap_present = detected_classes["tap"]
        concrete_present = detected_classes["concretepost"] or detected_classes["tap_junction"]
        platform_present = (
            detected_classes["platform"]
            or detected_classes["platform_with_objects"]
            or detected_classes["platformboundary"]
            or detected_classes["platform_notseenfull"]
            or detected_classes["platform_notseenfull_with_objects"]
            or detected_classes["cemented_floor"]
        )

        if tap_present and concrete_present and platform_present:
            tap["AI Tap Condition"] = "Good"
        elif not tap_present and concrete_present and platform_present:
            tap["AI Tap Condition"] = "Minor repair"
        elif tap_present and not concrete_present and platform_present:
            tap["AI Tap Condition"] = "Minor repair"
        elif not tap_present and not concrete_present and platform_present:
            tap["AI Tap Condition"] = "Major repair"
        elif not tap_present and platform_present and not concrete_present:
            tap["AI Tap Condition"] = "Major repair"
        elif not tap_present and not platform_present and concrete_present:
            tap["AI Tap Condition"] = "Reconstruction"
        elif not concrete_present and not platform_present and tap_present:
            tap["AI Tap Condition"] = "Reconstruction"
        elif not platform_present and tap_present and concrete_present:
            tap["AI Tap Condition"] = "Reconstruction"
        elif not tap_present and not concrete_present and not platform_present:
            tap["AI Tap Condition"] = "Reconstruction"
        else:
            tap["AI Tap Condition"] = "Unknown"

        # Add flag logic
        tap_condition_numeric = condition_map.get(tap.get("Tap Condition"), 0)
        ai_tap_condition_numeric = condition_map.get(tap["AI Tap Condition"], 0)

        if ai_tap_condition_numeric in [1, 2, 3, 4]:
            if tap_condition_numeric > ai_tap_condition_numeric:
                tap["Flag"] = "yellow"
            elif tap_condition_numeric < ai_tap_condition_numeric:
                tap["Flag"] = "red"
            elif tap_condition_numeric == ai_tap_condition_numeric:
                tap["Flag"] = "green"
        else:
            tap["Flag"] = "transparent"

        print(f"Flag for tap {index + 1}: {tap['Flag']}")

        # Update progress file
        progress["rows"].append({
            "index": index,
            "ai_condition": tap['AI Tap Condition'],
            "ai_predictions": tap['AI Predictions'],
            "flag": tap["Flag"]
        })

        with open(progress_path, 'w') as progress_file:
            json.dump(progress, progress_file)
            print(f"Progress updated for tap {index + 1}")

    # Mark as completed
    progress["status"] = "completed"
    with open(progress_path, 'w') as progress_file:
        json.dump(progress, progress_file)
    print(f"Processing completed for file: {file_name}")

    # Save updated JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"Updated JSON saved to: {json_path}")
