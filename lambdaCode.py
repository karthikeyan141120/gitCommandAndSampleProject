import os
import uuid
import json
import boto3
import openai
import subprocess
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont

# ---------- CONFIG ----------
BUCKET = os.environ.get("BUCKET_NAME")
openai.api_key = os.environ["OPENAI_API_KEY"]
FALLBACK_FACTS = [
    "முதல் கணினி எலி மரத்தால் செய்யப்பட்டது",
    "இணையம் முதலில் ராணுவ பயன்பாடு",
    "மொபைல் CPU மனிதனை விட வேகமானது",
    "AI மனிதனை விட வேகமாக கற்கிறது",
    "தரவு தான் புதிய எரிபொருள்",
    "மின்னஞ்சல் முதலில் 1971இல் பயன்படுத்தப்பட்டது",
    "சாட்ஜிபிடி மொழிகளை புரிந்து கொள்ளும்",
    "உலகின் முதல் இணையதளம் இன்னும் இயங்குகிறது",
    "கம்ப்யூட்டர் வைரஸ் 1986இல் உருவானது",
    "மேகம் தரவுகளை சேமிக்க பயன்படுகிறது"
]


s3 = boto3.client("s3")

def lambda_handler(event, context):
    """Generate Tamil tech video and upload to S3"""
    
    job_id = str(uuid.uuid4())[:8]
    print(f"🎬 Starting video generation: {job_id}")
    
    try:
        # Step 1: Generate Tamil fact
        print("📝 Generating Tamil tech fact...")
        facts = generate_tamil_fact()
        print(f" Fact: {facts}")
        # facts should be list[str]
        if not isinstance(facts, list):
            facts = []

        facts = [f.strip() for f in facts if isinstance(f, str) and len(f.strip()) > 5]

        if not facts:
            facts = FALLBACK_FACTS[:6]


        voice_text = ". ".join(facts)
        overlay_text = "\n".join(facts)
        # Step 2: Generate voice
        print("🎤 Generating Tamil voice...")
        audio_path = generate_voice(voice_text, job_id)
        # audio_duration = get_audio_duration(audio_path)
        # print(f"Audio: {audio_duration}s")
        
        # Step 3: Generate background image
        print("🎨 Generating background image...")
        bg_path = generate_background(job_id)
        print(f"Background created")
        
        # Step 4: Create text overlay
        print("Creating text overlay...")
        overlay_path = create_text_overlay(overlay_text, job_id)
        print(f"Overlay created")
        
        print("🎥 Composing video...")
        video_path = compose_video(bg_path, overlay_path, audio_path, 30, job_id)
        print(f"Video created")
        
        print("Uploading to S3...")
        s3_key = upload_to_s3(video_path, job_id, facts)
        print(f"Uploaded: s3://{BUCKET}/{s3_key}")
        
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET, 'Key': s3_key},
            ExpiresIn=3600
        )
        print(url)
        print("This is the final commit")
        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'job_id': job_id,
                'fact': overlay_text,
                's3_bucket': BUCKET,
                's3_key': s3_key,
                'download_url': url,
                'duration': 30
            }, ensure_ascii=False)
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'job_id': job_id
            })
        }


def download_file(url, timeout=30):
    """Download file using urllib"""
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req, timeout=timeout) as response:
            return response.read()
    except (URLError, HTTPError) as e:
        raise Exception(f"Failed to download: {str(e)}")


def extract_facts(raw_text):
    facts = []

    for line in raw_text.splitlines():
        line = line.strip()

        # remove numbering / bullets
        line = line.lstrip("0123456789.-•) ").strip()

        # basic sanity only (do NOT over-filter)
        if len(line) < 6:
            continue

        facts.append(line)

    return facts



def generate_tamil_fact():
    """Generate Tamil tech fact"""
    
#     prompt = """நீங்கள் ஒரு தொழில்நுட்ப கல்வியாளர். 

# ஒரு சுவாரஸ்யமான தொழில்நுட்ப உண்மையை தமிழில் உருவாக்குங்கள்.

# விதிகள்:
# - 20-30 வார்த்தைகள் மட்டும்
# - மிக எளிய தமிழ் மொழி
# - ஆச்சரியமான தகவல்

# உதாரணம்:
# "முதல் கணினி எலி 1964இல் மரத்தால் செய்யப்பட்டது!"

# இப்போது ஒரு புதிய உண்மை:"""
prompt = """
    நீங்கள் ஒரு தொழில்நுட்ப கல்வியாளர்.

    6 முதல் 10 வரை குறுகிய தொழில்நுட்ப உண்மைகளை தமிழில் உருவாக்குங்கள்.

    கட்டாய விதிகள்:
    - ஒவ்வொரு உண்மையும் முழுமையான வாக்கியம் ஆக இருக்க வேண்டும்
    - ஒவ்வொரு உண்மையும் 5–8 வார்த்தைகள்
    - எளிய மற்றும் சரியான தமிழ்
    - எண்கள், புள்ளிகள், குறிகள் வேண்டாம்
    - ஒவ்வொரு உண்மையும் புதிய வரியில் மட்டும்

    உதாரணம்:
    முதல் கணினி எலி மரத்தால் செய்யப்பட்டது
    இணையம் முதலில் ராணுவ பயன்பாடு
    மொபைல் CPU மனிதனை விட வேகமானது

    இப்போது 6–10 புதிய உண்மைகள் மட்டும்:
    """

MIN_FACTS = 6
MAX_FACTS = 10

max_attempts = 3
facts = []

for _ in range(max_attempts):
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        max_tokens=200
    )

    raw_text = response["choices"][0]["message"]["content"]
    facts = extract_facts(raw_text)

    if len(facts) >= MIN_FACTS:
        break

# 🔥 GUARANTEED FALLBACK
if len(facts) < MIN_FACTS:
    needed = MIN_FACTS - len(facts)
    facts.extend(FALLBACK_FACTS[:needed])

# cap to max
facts = facts[:MAX_FACTS]




    # return fact.strip('"').strip("'")


def generate_voice(text, job_id):
    """Generate Tamil voice"""
    audio_path = f"/tmp/audio_{job_id}.mp3"
    tts = gTTS(text=text, lang='ta', slow=False)
    tts.save(audio_path)
    return audio_path


def get_audio_duration(audio_path):
    """Get audio duration"""
    cmd = [
        "/opt/bin/ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def generate_background(job_id):
    """Generate background image"""
    prompt = """Vertical (9:16) tech background:
- Futuristic digital circuits
- Blue and purple neon lights
- Dark background
- No text"""

    response = openai.Image.create(
        prompt=prompt,
        n=1,
        size="512x512"
    )
    
    image_url = response['data'][0]['url']
    bg_path = f"/tmp/bg_{job_id}.png"
    
    img_data = download_file(image_url)
    with open(bg_path, 'wb') as f:
        f.write(img_data)
    
    return bg_path


def create_text_overlay(fact, job_id):
    """Create text overlay"""
    img = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Download Tamil font
    font_path = "/opt/fonts/NotoSansTamil-Bold.ttf"
    font = ImageFont.truetype(font_path, 64)

    
    # Word wrap
    words = fact.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = current_line + [word]
        bbox = draw.textbbox((0, 0), ' '.join(test_line), font=font)
        if bbox[2] > 950 and current_line:
            lines.append(' '.join(current_line))
            current_line = [word]
        else:
            current_line.append(word)
    
    if current_line:
        lines.append(' '.join(current_line))
    
    # Draw text
    line_height = 90
    total_height = len(lines) * line_height
    y_start = (1920 - total_height) // 2
    
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (1080 - text_width) // 2
        y = y_start + (i * line_height)
        
        # Outline
        for adj_x in range(-4, 5):
            for adj_y in range(-4, 5):
                draw.text((x + adj_x, y + adj_y), line, font=font, fill=(0, 0, 0, 255))
        
        # Text
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
    
    overlay_path = f"/tmp/overlay_{job_id}.png"
    img.save(overlay_path, 'PNG')
    return overlay_path


def compose_video(bg_path, overlay_path, audio_path, duration, job_id):
    """Compose video"""
    output_path = f"/tmp/video_{job_id}.mp4"
    video_duration = duration + 0.5
    
    cmd = [
        "/opt/bin/ffmpeg", "-y",
        "-loop", "1", "-i", bg_path,
        "-i", overlay_path,
        "-i", audio_path,
        "-filter_complex",
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "zoompan=z='min(zoom+0.0015,1.2)':d=1:s=1080x1920:fps=30[bg];"
        "[bg][1:v]overlay=0:0[v]",
        "-map", "[v]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-t", str(video_duration),
        "-movflags", "+faststart",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"FFmpeg failed: {result.stderr}")
    
    return output_path


def upload_to_s3(video_path, job_id, fact):
    """Upload to S3"""
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    s3_key = f"videos/{timestamp}_{job_id}.mp4"
    
    s3.upload_file(
        video_path,
        BUCKET,
        s3_key,
        ExtraArgs={
            'ContentType': 'video/mp4',
            'Metadata': {
                'job-id': job_id,
                'generated-at': timestamp
            }

        }
    )
    
    return s3_key
