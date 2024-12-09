import streamlit as st
import yt_dlp
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from twelvelabs import TwelveLabs
from twelvelabs.models.task import Task
import threading
import concurrent.futures
import time
from googleapiclient.discovery import build
from datetime import datetime, timezone
from datetime import datetime
import isodate
import re
import requests

from dotenv import load_dotenv


load_dotenv()


if 'setup_complete' not in st.session_state:
    st.session_state.setup_complete = False
if 'api_key' not in st.session_state:
    st.session_state.api_key = None

if 'index' not in st.session_state:
    st.session_state.index = None


if 'current_indexing' not in st.session_state:
    st.session_state.current_indexing = None
if 'indexed_count' not in st.session_state:
    st.session_state.indexed_count = 0
if 'total_videos' not in st.session_state:
    st.session_state.total_videos = 0


if 'fetched_videos' not in st.session_state:
    st.session_state.fetched_videos = None
if 'fetch_status' not in st.session_state:
    st.session_state.fetch_status = None

def get_downloads_folder():
    return str(Path.home() / "Downloads" / "YouTubeDownloads")

def index_video(file_path, index_id, client, status_placeholder):
    try:

        st.session_state.current_indexing = os.path.basename(file_path)
        status_placeholder.info(f"🎥 Currently indexing {st.session_state.current_indexing}")
        
        task = client.task.create(
            index_id=index_id,
            file=file_path,
        )
        
        progress_bar = status_placeholder.progress(0)
        start_time = time.time()
        
        def on_task_update(task: Task):
            elapsed_time = int(time.time() - start_time)
            if task.status == "processing":
                progress = min(0.95, elapsed_time / 180)  
                progress_bar.progress(progress)
            status_placeholder.info(f"""
            🎥 Currently indexing: {st.session_state.current_indexing}
            ⏳ Status: {task.status}
            ⌛ Time elapsed: {elapsed_time} seconds
            """)

        task.wait_for_done(sleep_interval=5, callback=on_task_update)
        progress_bar.progress(1.0)

        if task.status != "ready":
            return False, f"Indexing failed with status {task.status}"
            
        st.session_state.indexed_count += 1
        return True, task.video_id
    except Exception as e:
        return False, str(e)
def download_video(url):

    if not url:
        return None, None
    
    downloads_dir = get_downloads_folder()
    os.makedirs(downloads_dir, exist_ok=True)
    
    try:
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': os.path.join(downloads_dir, '%(title)s.%(ext)s'),
            'quiet': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename, info.get('title', '')
    except Exception as e:
        return None, str(e)
    


# def _get_api_key():
#        return st.session_state.api_key
def process_indexing_queue(queue, index_id, status_placeholder, api_key):

    try:
        client = TwelveLabs(api_key=api_key)
        successful_tasks = 0  
        
        while True:
            file_path = queue.get()
            if file_path is None:
                break
                
            try:
                print(f"Starting indexing for: {file_path}")
                
                task = client.task.create(
                    index_id=index_id,
                    file=file_path,
                )
                
                print(f"Task created with ID: {task.id}")
            
                def on_task_update(task: Task):
                    print(f"  Status={task.status}")
                    if task.status == "ready":
                        nonlocal successful_tasks
                        successful_tasks += 1
                
         
                task.wait_for_done(sleep_interval=5, callback=on_task_update)
                
                if task.status == "ready":
                    print(f"The unique identifier of your video is {task.video_id}")
                else:
                    print(f"Task failed with status: {task.status}")
                
            except Exception as e:
                print(f"Error during indexing: {str(e)}")
            finally:
                queue.task_done()
        
     
        return successful_tasks
        
    except Exception as e:
        print(f"Error in indexing queue: {str(e)}")
        return 0

def video_urls_section():

    st.header("Video URLs")
    
    urls = []
    for i in range(5):
        url = st.text_input(f"Video URL #{i+1}:", key=f"url_{i}")
        urls.append(url)

    if st.button("Download and Index"):
        if not st.session_state.api_key:
            st.error("⚠️ API key not found. Please complete the setup first.")
            return
            
        if not st.session_state.index:
            st.error("⚠️ Index not found. Please complete the setup first.")
            return
            
        valid_urls = [url for url in urls if url]
        if not valid_urls:
            st.warning("Please enter at least one URL!")
            return
        
        api_key = st.session_state.api_key
        index_id = st.session_state.index.id
        
        total_videos = len(valid_urls)
        downloads_dir = get_downloads_folder()
        st.info(f"📂 Videos will be saved to {downloads_dir}")
        
        status_container = st.container()
        downloaded_files = []
        
        try:
            with st.spinner("Processing videos..."):
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = []
                    for i, url in enumerate(valid_urls):
                        future = executor.submit(download_video, url)
                        futures.append((future, i, url))
                    
                    for future, i, url in futures:
                        try:
                            filename, title_or_error = future.result()
                            if filename and os.path.exists(filename):
                                st.success(f"✅ Downloaded: {title_or_error}")
                                downloaded_files.append((filename, title_or_error))
                            else:
                                st.error(f"❌ Error downloading video #{i+1}: {title_or_error}")
                        except Exception as e:
                            st.error(f"❌ Error processing video #{i+1}: {str(e)}")

                if downloaded_files:
                    st.info("🔄 Starting indexing process...")
                    successful_indexes = 0
                    
                    for filename, title in downloaded_files:
                        try:
                            with status_container:
                                client = TwelveLabs(api_key=api_key)
                                st.info(f"🔍 Indexing: {title}")
                                progress_bar = st.progress(0)
                                
                                task = client.task.create(
                                    index_id=index_id,
                                    file=filename
                                )
                                
                                start_time = time.time()
                                
                                def on_task_update(task: Task):
                                    elapsed_time = int(time.time() - start_time)
                                    if task.status == "processing":
                                        progress = min(0.95, elapsed_time / 180)
                                        progress_bar.progress(progress)
                                
                                task.wait_for_done(sleep_interval=5, callback=on_task_update)
                                
                                if task.status == "ready":
                                    progress_bar.progress(1.0)
                                    st.success(f"""
                                    ✅ Successfully indexed: {title}
                                    🎯 Video ID: {task.video_id}
                                    ⌛ Total time: {int(time.time() - start_time)} seconds
                                    """)
                                    successful_indexes += 1
                                else:
                                    st.error(f"❌ Indexing failed for {title} with status: {task.status}")
                                    
                        except Exception as e:
                            st.error(f"❌ Indexing error for {title}: {str(e)}")
                    
                    if successful_indexes > 0:
                        st.success(f"✅ Successfully indexed {successful_indexes} out of {len(downloaded_files)} videos")
                    else:
                        st.error("❌ No videos were successfully indexed")
                else:
                    st.error("❌ No videos were successfully downloaded")
                    
        except Exception as e:
            st.error(f"❌ Error during processing: {str(e)}")

def get_channel_videos(channel_url, option, video_count):
    try:
        if option == "most_recent":
            ydl_opts = {
                'extract_flat': 'in_playlist',
                'quiet': True,
                'no_warnings': True,
                'playlistend': video_count * 2,  # Fetch extra to account for potential errors
                'playlist_items': f'1:{video_count * 2}',
                'ignoreerrors': True,
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash', 'hls'],
                        'player_skip': ['js', 'configs', 'webpage']
                    }
                }
            }

            channel_url = f"{channel_url}/videos?view=0&sort=dd&flow=grid"
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                channel_info = ydl.extract_info(channel_url, download=False)
                
                if not channel_info:
                    return False, "Could not fetch channel information"

                videos = []
                if 'entries' in channel_info:
                    videos = [entry for entry in channel_info['entries'] if entry is not None]
                
                if not videos:
                    return False, "No videos found in channel"

                videos = videos[:video_count]

                video_info = []
                for video in videos:
                    if video and 'id' in video:
                        url = f"https://www.youtube.com/watch?v={video['id']}"
                        title = video.get('title', 'Untitled')
                        view_count = video.get('view_count', 'N/A')
                        video_info.append({
                            'url': url,
                            'title': title,
                            'views': view_count
                        })

                if not video_info:
                    return False, "Could not extract valid video URLs"

                return True, video_info

        else:
            channel_id = get_channel_id_from_url(channel_url)
            if not channel_id:
                return False, "Could not extract channel ID"
            
            if option == "oldest":
                return get_old_videos(channel_id, video_count)
            elif option == "most_viewed":
                return get_popular_videos(channel_id, video_count)

    except Exception as e:
        return False, f"Error: {str(e)}"
    

def fetch_existing_indexes(api_key):

    url = "https://api.twelvelabs.io/v1.3/indexes"
    headers = {
        "accept": "application/json",
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            url,
            headers=headers,
            params={"page": 1, "page_limit": 50, "sort_by": "created_at", "sort_option": "desc"}
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching indexes: {str(e)}")
        return None

def format_index_info(index):

    models = [model["model_name"] for model in index["models"]]
    expires = datetime.strptime(index["expires_at"], "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%Y-%m-%d")
    
    return {
        "id": index["_id"],
        "name": index["index_name"],
        "video_count": index["video_count"],
        "models": ", ".join(models),
        "expires": expires
    }

def get_channel_id_from_url(channel_url):

    youtube = build('youtube', 'v3', developerKey=os.getenv('YOUTUBE_API_KEY'))
    
    try:

        if '/channel/' in channel_url:
            return channel_url.split('/channel/')[-1].split('/')[0]
        
        elif '/@' in channel_url:
            custom_handle = channel_url.split('/@')[-1].split('/')[0]
            

            request = youtube.search().list(
                part="snippet",
                q=custom_handle,
                type="channel",
                maxResults=1
            )
            response = request.execute()
            
            if response.get('items'):
                channel_id = response['items'][0]['snippet']['channelId']
                print(f"Found channel ID: {channel_id} for handle: {custom_handle}")
                return channel_id
        
        request = youtube.search().list(
            part="snippet",
            q=channel_url,
            type="channel",
            maxResults=1
        )
        response = request.execute()
        
        if response.get('items'):
            channel_id = response['items'][0]['snippet']['channelId']
            print(f"Found channel ID through search: {channel_id}")
            return channel_id
        
        return None
        
    except Exception as e:
        print(f"Error in get_channel_id_from_url: {str(e)}")  
        return None

def get_old_videos(channel_id, limit=10):

    youtube = build('youtube', 'v3', developerKey=os.getenv('YOUTUBE_API_KEY'))
    
    try:

        channel_response = youtube.channels().list(
            part="statistics,contentDetails",
            id=channel_id
        ).execute()
        
        if not channel_response.get('items'):
            return False, "Channel not found"
            
        total_videos = int(channel_response['items'][0]['statistics']['videoCount'])
        uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        print(f"Channel has {total_videos} total videos")
        
        items_per_page = 50
        pages_to_skip = (total_videos - 50) // items_per_page
        
        next_page_token = None
        current_page = 0
        
        while current_page < pages_to_skip:
            response = youtube.playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
            current_page += 1
            print(f"Skipping page {current_page}/{pages_to_skip}")
        
        final_response = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=next_page_token
        ).execute()

        videos_data = []
        for item in final_response['items']:
            publish_date = item['snippet']['publishedAt']
            video_id = item['snippet']['resourceId']['videoId']
            videos_data.append({
                'video_id': video_id,
                'publish_date': publish_date,
                'title': item['snippet']['title']
            })
        
        videos_data.sort(key=lambda x: x['publish_date'])
        
        final_videos = []
        for video in videos_data[:limit]:
            video_response = youtube.videos().list(
                part="statistics,snippet",
                id=video['video_id']
            ).execute()
            
            if video_response['items']:
                video_details = video_response['items'][0]
                publish_date = video_details['snippet']['publishedAt']
                formatted_date = datetime.fromisoformat(publish_date.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                
                video_info = {
                    'url': f"https://www.youtube.com/watch?v={video['video_id']}",
                    'title': video_details['snippet']['title'],
                    'views': int(video_details['statistics']['viewCount']),
                    'published': formatted_date
                }
                final_videos.append(video_info)
                print(f"Found oldest video: {video_info['title']} (Published: {formatted_date})")
        
        final_videos.sort(key=lambda x: x['published'])
        return True, final_videos[:limit]
        
    except Exception as e:
        print(f"Error in get_old_videos: {str(e)}")
        return False, f"Error fetching old videos: {str(e)}"

def get_popular_videos(channel_id, limit=10):
    youtube = build('youtube', 'v3', developerKey=os.getenv('YOUTUBE_API_KEY'))
    
    try:
        print(f"Fetching popular videos for channel ID: {channel_id}")
        
        request = youtube.search().list(
            part="id,snippet",
            channelId=channel_id,
            maxResults=limit,
            order="viewCount", 
            type="video"
        )
        response = request.execute()
        
        print(f"Initial API response: {response.get('pageInfo')}")
        
        videos = []
        if 'items' in response:
            for item in response['items']:
                video_id = item['id']['videoId']
                
                video_request = youtube.videos().list(
                    part="statistics,snippet",
                    id=video_id
                )
                video_response = video_request.execute()
                
                if video_response['items']:
                    video_details = video_response['items'][0]
                    video_info = {
                        'url': f"https://www.youtube.com/watch?v={video_id}",
                        'title': video_details['snippet']['title'],
                        'views': int(video_details['statistics']['viewCount'])
                    }
                    videos.append(video_info)
                    print(f"Added video: {video_info['title']} with {video_info['views']} views")  # Debug log
        
        videos.sort(key=lambda x: x['views'], reverse=True)
        return True, videos[:limit]
        
    except Exception as e:
        print(f"Error in get_popular_videos: {str(e)}")  
        return False, f"Error fetching popular videos: {str(e)}"

def process_videos(video_info, download_status, indexing_status):
    try:
        client = TwelveLabs(api_key=st.session_state.api_key)
        video_urls = [info['url'] for info in video_info]
        st.session_state.total_videos = len(video_urls)
        st.session_state.indexed_count = 0
        downloads_dir = get_downloads_folder()
        st.info(f"📂 Videos will be saved to: {downloads_dir}")

        downloaded_files = {}
        status_containers = {}
        for i in range(len(video_info)):
            status_containers[i] = st.container()

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_video = {
                executor.submit(download_video, info['url']): (i, info)
                for i, info in enumerate(video_info)
            }

            for future in concurrent.futures.as_completed(future_to_video):
                i, info = future_to_video[future]
                try:
                    filename, title = future.result()
                    if filename and os.path.exists(filename):
                        with status_containers[i]:
                            st.success(f"""
                            ✅ Video #{i + 1}: Downloaded
                            📁 File: {title}
                            """)
                        downloaded_files[i] = (filename, title)
                    else:
                        with status_containers[i]:
                            st.error(f"❌ Video #{i + 1}: Download failed - {title}")
                except Exception as e:
                    with status_containers[i]:
                        st.error(f"❌ Video #{i + 1}: Download error - {str(e)}")


        st.info("🔄 Starting indexing process for downloaded videos...")
        
        for i, (filename, title) in downloaded_files.items():
            try:
                with status_containers[i]:
                    st.info(f"🔍 Starting indexing for: {title}")
                    progress_bar = st.progress(0)
                    
                    task = client.task.create(
                        index_id=st.session_state.index.id, 
                        file=filename
                    )
                    
                    start_time = time.time()
                    
                    def on_task_update(task: Task):
                        elapsed_time = int(time.time() - start_time)
                        if task.status == "processing":
                            progress = min(0.95, elapsed_time / 180)
                            progress_bar.progress(progress)
                            st.info(f"""
                            🎥 Currently indexing: {title}
                            ⏳ Status: {task.status}
                            ⌛ Time elapsed: {elapsed_time} seconds
                            """)
                    
                    task.wait_for_done(sleep_interval=5, callback=on_task_update)
                    
                    if task.status == "ready":
                        progress_bar.progress(1.0)
                        st.success(f"""
                        ✅ Successfully indexed: {title}
                        🎯 Video ID: {task.video_id}
                        ⌛ Total time: {int(time.time() - start_time)} seconds
                        """)
                        st.session_state.indexed_count += 1
                    else:
                        st.error(f"❌ Indexing failed for {title} with status: {task.status}")
                
            except Exception as e:
                with status_containers[i]:
                    st.error(f"❌ Indexing error for {title}: {str(e)}")

        st.success(f"""
        ✅ All processing completed!
        📊 Total videos indexed: {st.session_state.indexed_count}/{len(downloaded_files)}
        📁 Videos saved in: {downloads_dir}
        """)
        return True

    except Exception as e:
        st.error(f"❌ Error during processing: {str(e)}")
        return False
    


def channel_videos_section():
    st.header("Channel Videos")
    
    if not st.session_state.index:
        st.warning("Please create an index in the Video URLs tab first!")
        return
    
    channel_url = st.text_input(
        "Enter YouTube Channel URL:",
        placeholder="https://www.youtube.com/channel/... or https://www.youtube.com/@..."
    )
    
    video_count = st.slider(
        "Number of videos to process:",
        min_value=1,
        max_value=100,
        value=10,
        help="Select how many videos you want to process"
    )
    
    option = st.selectbox(
        "Select videos to process:",
        [
            "most_recent",
            "most_viewed",
            "oldest"
        ],
        format_func=lambda x: {
            "most_recent": "Most Recent Videos",
            "most_viewed": "Most Viewed Videos",
            "oldest": "Oldest Videos"
        }[x]
    )
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("Fetch Videos"):
            if not channel_url:
                st.warning("Please enter a channel URL!")
                return
                
            with st.spinner("Fetching channel videos..."):
                success, result = get_channel_videos(channel_url, option, video_count)
                
                if success:
                    st.session_state.fetched_videos = result
                    st.session_state.fetch_status = 'success'
                else:
                    st.session_state.fetch_status = 'error'
                    st.error(f"Error fetching videos: {result}")
    
    if st.session_state.fetch_status == 'success' and st.session_state.fetched_videos:
        st.success(f"Found {len(st.session_state.fetched_videos)} videos to process")
        
        with st.expander("Preview videos to be processed", expanded=True):
            for i, info in enumerate(st.session_state.fetched_videos, 1):
                st.markdown(f"""
                **{i}. {info['title']}**
                - URL: {info['url']}
                - Views: {info.get('views', 'N/A')}
                {f"- Published: {info.get('published', 'N/A')}" if 'published' in info else ''}
                """)
        
        with col2:
            if st.button("Process Videos"):
                download_status = st.empty()
                indexing_status = st.empty()
                
                with st.spinner("Processing videos..."):
                    process_videos(
                        st.session_state.fetched_videos,
                        download_status,
                        indexing_status
                    )


def initial_setup():
    st.title("Index UGC with Twelve Labs")
    
    api_key = st.text_input(
        "Enter your Twelve Labs API Key:",
        value="", 
        type="password",
        help="Your API key from the Twelve Labs dashboard"
    )

    if not api_key:
        st.warning("Please enter your API key to proceed")
        return

    existing_indexes = None
    if api_key:
        with st.spinner("Fetching existing indexes..."):
            existing_indexes = fetch_existing_indexes(api_key)

    index_option = st.radio(
        "Choose an option:",
        ["Create New Index", "Use Existing Index"],
        help="Create a new index or select from your existing ones"
    )

    if index_option == "Create New Index":
        st.subheader("Create New Index")
        
        index_name = st.text_input(
            "Enter Index Name:",
            help="Choose a unique name for your video index"
        )

        st.info("Marengo 2.7 as the default model for all indexes.")
        use_pegasus = st.checkbox("Add Pegasus 1.1 to enhance indexing capabilities")
        
        if st.button("Create New Index"):
            if not index_name:
                st.error("⚠️ Please enter an index name")
                return
                
            try:
                with st.spinner("Creating new index..."):
                    client = TwelveLabs(api_key=api_key)
                    
                    models = [
                        {
                            "name": "marengo2.7",
                            "options": ["visual", "audio"]
                        }
                    ]
                    
                    if use_pegasus:
                        models.insert(0, {
                            "name": "pegasus1.1",
                            "options": ["visual", "audio"]
                        })
                    
                    index = client.index.create(
                        name=index_name,
                        models=models,
                        addons=["thumbnail"]
                    )
                    
                    st.session_state.api_key = api_key
                    st.session_state.index = index
                    st.session_state.setup_complete = True
                    
                    model_names = [model["name"] for model in models]
                    st.success(f"""
                    ✅ New index created successfully!
                    📊 Active Models: {", ".join(model_names)}
                    """)
                    time.sleep(1)
                    st.rerun()
                    
            except Exception as e:
                st.error(f"❌ Index creation failed: {str(e)}")

    else: 
        st.subheader("Select Existing Index")
        
        if existing_indexes and "data" in existing_indexes:
            index_options = {
                f"{index['index_name']} (Videos: {index['video_count']})": format_index_info(index)
                for index in existing_indexes["data"]
            }
            
            selected_index = st.selectbox(
                "Choose an index:",
                options=list(index_options.keys()),
                format_func=lambda x: x
            )
            
            if selected_index:
                index_info = index_options[selected_index]
                
                st.info(f"""
                **Selected Index Details:**
                - Name: {index_info['name']}
                - Videos: {index_info['video_count']}
                - Models: {index_info['models']}
                - Expires: {index_info['expires']}
                """)
                
                if st.button("Use Selected Index"):
                    try:
                        client = TwelveLabs(api_key=api_key)
                        
                        st.session_state.api_key = api_key
                        st.session_state.index = index_info['id']
                        st.session_state.setup_complete = True
                        
                        st.success(f"✅ Successfully connected to index: {index_info['name']}")
                        time.sleep(1)
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error connecting to index: {str(e)}")
        else:
            st.warning("No existing indexes found or error fetching indexes")

def main():
    if not st.session_state.setup_complete or not st.session_state.index:
        initial_setup()
        return
    
    st.title("Index UGC with Twelve Labs")
    
    with st.sidebar:
        st.success(f"✅ Active Index: {st.session_state.index}")
        if st.button("Switch Index"):
            st.session_state.setup_complete = False
            st.session_state.index = None
            st.rerun()
    
    tab1, tab2 = st.tabs(["Video URLs", "Channel Videos"])
    
    with tab1:
        video_urls_section()
    
    with tab2:
        channel_videos_section()

if __name__ == "__main__":
    main()