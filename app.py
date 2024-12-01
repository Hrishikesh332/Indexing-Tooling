import streamlit as st
import yt_dlp
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from twelvelabs import TwelveLabs
from twelvelabs.models.task import Task
import threading
import time
# Initialize session state
if 'index' not in st.session_state:
    st.session_state.index = None
if 'current_indexing' not in st.session_state:
    st.session_state.current_indexing = None
if 'indexed_count' not in st.session_state:
    st.session_state.indexed_count = 0
if 'total_videos' not in st.session_state:
    st.session_state.total_videos = 0
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
def download_video(url, index_queue):
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
            index_queue.put(filename)
            return filename, info.get('title', '')
    except Exception as e:
        return None, str(e)
def process_indexing_queue(queue, index_id, status_placeholder):
    client = TwelveLabs(api_key="tlk_32YBVAW1GVJHV42ASQ5KB3WEJYW1")
    
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
            
            engines = [
                {
                    "name": "marengo2.6",
                    "options": ["visual", "conversation", "text_in_video", "logo"]
                }
            ]
            
            try:
                index = client.index.create(
                    name=index_name,
                    engines=engines,
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
def channel_videos_section():
    st.header("Channel Videos")
    st.info("Still in Progress")
def main():
    st.title("YouTube Video Processor and Indexing")
    tab1, tab2 = st.tabs(["Video URLs", "Channel Videos"])
    
    with tab1:
        video_urls_section()
    
    with tab2:
        channel_videos_section()
if __name__ == "__main__":
    main()
