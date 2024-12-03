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
from dotenv import load_dotenv


load_dotenv()

API_KEY = os.getenv("API_KEY")

# Initialize session state
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
        status_placeholder.info(f"🎥 Currently indexing: {st.session_state.current_indexing}")
        
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
    """Download a video without using queue"""
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

def process_indexing_queue(queue, index_id, status_placeholder):
    client = TwelveLabs(api_key=API_KEY)
    
    while True:
        file_path = queue.get()
        if file_path is None:
            break
            
        success, result = index_video(file_path, index_id, client, status_placeholder)
        
        if success:
            status_placeholder.success(f"""
            ✅ Successfully indexed: {os.path.basename(file_path)}
            🎯 Video ID: {result}
            📊 Progress: {st.session_state.indexed_count}/{st.session_state.total_videos}
            """)
        else:
            status_placeholder.error(f"❌ Indexing failed for {os.path.basename(file_path)}: {result}")
        
        queue.task_done()

def video_urls_section():
    st.header("Video URLs")

    index_name = st.text_input("Enter Index Name:", key="index_name")

    if st.button("Create Index") and index_name and not st.session_state.index:
        with st.spinner("Creating index..."):
            client = TwelveLabs(api_key=API_KEY)
            
            models = [
                {
                    "name": "marengo2.6",
                    "options": ["visual", "conversation", "text_in_video", "logo"]
                }
            ]
            
            try:
                index = client.index.create(
                    name=index_name,
                    models=models,
                    addons=["thumbnail"]
                )
                st.session_state.index = index
                st.success(f"Index created successfully! ID: {index.id}")
            except Exception as e:
                st.error(f"Failed to create index: {str(e)}")
                return
    
    if not st.session_state.index:
        st.warning("Please create an index first!")
        return
 
    urls = []
    for i in range(5):
        url = st.text_input(f"Video URL #{i+1}:", key=f"url_{i}")
        urls.append(url)

    if st.button("Download and Index"):
        valid_urls = [url for url in urls if url]
        if not valid_urls:
            st.warning("Please enter at least one URL!")
            return
            
        st.session_state.total_videos = len(valid_urls)
        st.session_state.indexed_count = 0
        downloads_dir = get_downloads_folder()
        st.info(f"📂 Videos will be saved to {downloads_dir}")
        
        download_status = st.empty()
        indexing_status = st.empty()
        
        index_queue = Queue()
        indexing_thread = threading.Thread(
            target=process_indexing_queue,
            args=(index_queue, st.session_state.index.id, indexing_status)
        )
        indexing_thread.start()
        
        with st.spinner("Processing videos..."):
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_url = {
                    executor.submit(download_video, url, index_queue): (i, url)
                    for i, url in enumerate(valid_urls)
                }
                
                for future in future_to_url:
                    i, url = future_to_url[future]
                    filename, title_or_error = future.result()
                    
                    if filename and os.path.exists(filename):
                        download_status.success(f"✅ Downloaded: {title_or_error}")
                    elif url:
                        download_status.error(f"❌ Error downloading video #{i+1}: {title_or_error}")
        

        index_queue.put(None)
        indexing_thread.join()
        st.success(f"""
        ✅ All processing completed!
        📊 Total videos processed: {st.session_state.indexed_count}/{st.session_state.total_videos}
        """)


def get_channel_videos(channel_url, option):
    """Extract videos from channel based on selected option"""
    try:
        limit = 5 if option == "5_newest" else 10

        ydl_opts = {
            'extract_flat': 'in_playlist',
            'quiet': True,
            'no_warnings': True,
            'playlistend': limit * 2,
            'playlist_items': f'1:{limit * 2}',
            'ignoreerrors': True,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],
                    'player_skip': ['js', 'configs', 'webpage']
                }
            }
        }

 
        if "oldest" in option:
            ydl_opts['playlistreverse'] = True
        elif "popular" in option:
            channel_url = f"{channel_url}/videos?view=0&sort=p&flow=grid"
        else:  
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

            if option == "10_popular":
                videos.sort(key=lambda x: x.get('view_count', 0) if x.get('view_count') is not None else 0, reverse=True)

            videos = videos[:limit]

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

    except Exception as e:
        return False, f"Error: {str(e)}"


def process_videos(video_info, download_status, indexing_status):

    try:
        client = TwelveLabs(api_key=API_KEY)
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
    
    option = st.selectbox(
        "Select videos to process:",
        [
            "5_newest",
            "10_newest",
            "10_oldest",
            "10_popular"
        ],
        format_func=lambda x: {
            "5_newest": "5 Newest Videos",
            "10_newest": "10 Newest Videos",
            "10_oldest": "10 Oldest Videos",
            "10_popular": "10 Most Popular Videos"
        }[x]
    )
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("Fetch Videos"):
            if not channel_url:
                st.warning("Please enter a channel URL!")
                return
                
            with st.spinner("Fetching channel videos..."):
                success, result = get_channel_videos(channel_url, option)
                
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
                - Views: {info['views']}
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


def main():
    st.title("YouTube Video Processor and Indexing")

    tab1, tab2 = st.tabs(["Video URLs", "Channel Videos"])
    
    with tab1:
        video_urls_section()
    
    with tab2:
        channel_videos_section()

if __name__ == "__main__":
    main()
