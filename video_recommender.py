import requests

YOUTUBE_API_KEY = "AIzaSyDlWYVSOFgrEOe4QnGeP3JhBzUWqfb3lxQ"
KKHSOU_CHANNEL_ID  = "UCGvoIhFaB3OiRZqpti0eFnw"

# ------------------ SEARCH ------------------
def search_videos(topic, max_results=3):
    """
    Search YouTube videos only from KKHSOU channel.
    Returns list of embeddable video results.
    """
    if not topic or len(topic.strip()) < 2:
        return []

    query = f"KKHSOU {topic}"

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "channelId": KKHSOU_CHANNEL_ID,
        "key": YOUTUBE_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        videos = []

        for item in data.get("items", []):
            video_id = item["id"].get("videoId")
            title = item["snippet"].get("title", "Untitled Video")

            if not video_id:
                continue

            videos.append({
                "title": title,
                "url": f"https://www.youtube.com/embed/{video_id}"
            })

        return videos

    except Exception as e:
        print(f"YouTube API error for topic '{topic}': {e}")
        return []