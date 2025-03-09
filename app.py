import streamlit as st
import yt_dlp
from pytube import YouTube
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

from queue import Queue, Empty 
import threading
import concurrent.futures
import os
from pathlib import Path


import youtube_dl

import os
import yt_dlp
from moviepy.editor import VideoFileClip
from pathlib import Path
import math
import time
import shutil
import tempfile


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


def delete_file(file_path):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
    except Exception as e:
        print(f"Error deleting file {file_path}: {str(e)}")
    return False

if 'need_chunking_for_pegasus' not in st.session_state:
    st.session_state.need_chunking_for_pegasus = False


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

        if task.status == "ready":
            delete_file(file_path)
            st.session_state.indexed_count += 1
            return True, task.video_id
        else:
            return False, f"Indexing failed with status {task.status}"
            
    except Exception as e:
        return False, str(e)

def download_video(url):
    if not url:
        return None, None
    
    downloads_dir = get_downloads_folder()
    os.makedirs(downloads_dir, exist_ok=True)
    
    try:
        ydl_opts = {
            'format': 'mp4',  # Simple format selection
            'outtmpl': os.path.join(downloads_dir, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                meta = ydl.extract_info(url, download=False)
                if meta:
                    download_url = meta.get('url')
                    if download_url:
                        info = ydl.extract_info(url, download=True)
                        if info:
                            filename = ydl.prepare_filename(info)
                            if os.path.exists(filename):
                                return filename, info.get('title', '')
                

                ydl_opts['format'] = 'best'
                info = ydl.extract_info(url, download=True)
                if info:
                    filename = ydl.prepare_filename(info)
                    if os.path.exists(filename):
                        return filename, info.get('title', '')
                
            except Exception as e:
                print(f"Error during download: {str(e)}")
                
            return None, "Could not download video"
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
                        delete_file(file_path)
                
         
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

    # Display a note about video chunking if Pegasus is enabled
    if st.session_state.need_chunking_for_pegasus:
        st.info("ℹ️ Pegasus model is active. Videos longer than 59 minutes will be automatically chunked.")

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
                                
                                # Check if the video needs chunking for Pegasus
                                needs_chunking = st.session_state.need_chunking_for_pegasus
                                
                                if needs_chunking:
                                    # Check video duration
                                    duration = get_video_duration(filename)
                                    if duration and duration > (59*60):  # 59 minutes in seconds
                                        st.info(f"📏 Video length: {duration/60:.1f} minutes. Video will be chunked.")
                                    else:
                                        st.info(f"📏 Video length: {duration/60:.1f} minutes. No chunking needed.")
                                
                                progress_bar = st.progress(0)
                                
                                # Use the enhanced function that supports chunking
                                success, result = index_video_with_chunking(
                                    file_path=filename,
                                    index_id=index_id,
                                    client=client,
                                    status_placeholder=status_container,
                                    needs_chunking=needs_chunking
                                )
                                
                                if success:
                                    st.success(f"""
                                    ✅ Successfully indexed: {title}
                                    🎯 Result: {result}
                                    """)
                                    successful_indexes += 1
                                else:
                                    st.error(f"❌ Indexing failed for {title}: {result}")
                                    
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



def get_channel_videos(channel_url, option):
 
    try:
  
        if option in ["5_newest", "10_newest"]:
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

        else:
            channel_id = get_channel_id_from_url(channel_url)
            if not channel_id:
                return False, "Could not extract channel ID"
            
            if option == "10_oldest":
                return get_old_videos(channel_id, 10)
            elif option == "10_popular":
                return get_popular_videos(channel_id, 10)

    except Exception as e:
        return False, f"Error: {str(e)}"

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




def get_video_duration(file_path):

    try:
        clip = VideoFileClip(file_path)
        duration = clip.duration
        clip.close()
        return duration
    except Exception as e:
        print(f"Error getting video duration: {str(e)}")
        return None

def chunk_video(input_path, output_dir, chunk_duration=59*60, status_placeholder=None):

    try:
        os.makedirs(output_dir, exist_ok=True)
        
        if status_placeholder:
            status_placeholder.info("📊 Analyzing video file...")
        
        video = VideoFileClip(input_path)
        total_duration = video.duration
        video.close()
        
        num_chunks = math.ceil(total_duration / chunk_duration)
        
        if num_chunks <= 1:
            if status_placeholder:
                status_placeholder.success("✅ Video is already within time limit. No chunking needed.")
            return [input_path]
            
        if status_placeholder:
            status_placeholder.info(f"""
            📋 Chunking Plan:
            - Video Duration: {total_duration/60:.1f} minutes
            - Chunk Duration: {chunk_duration/60:.1f} minutes
            - Total Chunks: {num_chunks}
            """)
            
            chunking_progress = status_placeholder.progress(0)
            
        chunk_files = []
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        
        for i in range(num_chunks):
            start_time = i * chunk_duration
            end_time = min((i + 1) * chunk_duration, total_duration)
            
            if status_placeholder:
                status_placeholder.info(f"🔪 Creating chunk {i+1}/{num_chunks}: {start_time/60:.1f} - {end_time/60:.1f} minutes")
            
            chunk_path = os.path.join(output_dir, f"{base_name}_chunk_{i+1}.mp4")
            
            with VideoFileClip(input_path) as video:
                new_clip = video.subclip(start_time, end_time)
                new_clip.write_videofile(
                    chunk_path, 
                    codec="libx264",
                    audio_codec="aac",
                    temp_audiofile=os.path.join(tempfile.gettempdir(), f"temp_audio_{i}.m4a"),
                    remove_temp=True,
                    verbose=False,
                    logger=None 
                )
            
            chunk_files.append(chunk_path)
            
            if status_placeholder and 'chunking_progress' in locals():
                overall_progress = (i + 1) / num_chunks
                chunking_progress.progress(overall_progress)
                status_placeholder.success(f"✅ Chunk {i+1}/{num_chunks} completed")
            
        if status_placeholder:
            status_placeholder.success(f"✅ Video chunking complete! Created {len(chunk_files)} chunks.")
            
        return chunk_files
        
    except Exception as e:
        if status_placeholder:
            status_placeholder.error(f"❌ Error during chunking: {str(e)}")
        print(f"Error chunking video: {str(e)}")
        return []

def process_video_for_pegasus(file_path, index_id, client, max_duration=59*60):

    try:
        duration = get_video_duration(file_path)
        
        if not duration:
            return 0, 1, []
            
        if duration <= max_duration:
            task = client.task.create(
                index_id=index_id,
                file=file_path,
            )
            
            task.wait_for_done(sleep_interval=5)
            
            if task.status == "ready":
                return 1, 0, [task.video_id]
            else:
                return 0, 1, []
                
        chunks_dir = os.path.join(os.path.dirname(file_path), "chunks")
        chunk_paths = chunk_video(file_path, chunks_dir, max_duration)
        
        success_count = 0
        failure_count = 0
        video_ids = []
        
        for chunk_path in chunk_paths:
            try:
                task = client.task.create(
                    index_id=index_id,
                    file=chunk_path,
                )
                
                task.wait_for_done(sleep_interval=5)
                
                if task.status == "ready":
                    success_count += 1
                    video_ids.append(task.video_id)
                else:
                    failure_count += 1
                    
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)
                    
            except Exception as e:
                print(f"Error indexing chunk {chunk_path}: {str(e)}")
                failure_count += 1
                
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)
        
        try:
            if os.path.exists(chunks_dir):
                shutil.rmtree(chunks_dir)
        except:
            pass
            
        return success_count, failure_count, video_ids
        
    except Exception as e:
        print(f"Error in process_video_for_pegasus: {str(e)}")
        return 0, 1, []




def index_video_with_chunking(file_path, index_id, client, status_placeholder=None, needs_chunking=False):

    try:
        if status_placeholder:
            st.session_state.current_indexing = os.path.basename(file_path)
            status_placeholder.info(f"🎥 Currently processing: {st.session_state.current_indexing}")
        
        if not needs_chunking:
            if status_placeholder:
                status_placeholder.info("📤 Uploading video to Twelve Labs API...")
                progress_bar = status_placeholder.progress(0)
            
            task = client.task.create(
                index_id=index_id,
                file=file_path,
            )
            
            start_time = time.time()
            
            def on_task_update(task):
                elapsed_time = int(time.time() - start_time)
                if task.status == "processing" and status_placeholder:
                    progress = min(0.95, elapsed_time / 180)
                    if 'progress_bar' in locals():
                        progress_bar.progress(progress)
                if status_placeholder:
                    status_placeholder.info(f"""
                    🎥 Currently indexing: {st.session_state.current_indexing}
                    ⏳ Status: {task.status}
                    ⌛ Time elapsed: {elapsed_time} seconds
                    """)

            task.wait_for_done(sleep_interval=5, callback=on_task_update)
            
            if status_placeholder and 'progress_bar' in locals():
                progress_bar.progress(1.0)

            if task.status == "ready":
                delete_file(file_path)
                if 'indexed_count' in st.session_state:
                    st.session_state.indexed_count += 1
                return True, task.video_id
            else:
                return False, f"Indexing failed with status {task.status}"
        else:
            if status_placeholder:
                status_placeholder.info(f"📏 Checking if video needs chunking...")
            
            duration = get_video_duration(file_path)
            max_duration = 59 * 60
            
            if not duration:
                return False, "Could not determine video duration"
                
            if duration <= max_duration:
                if status_placeholder:
                    status_placeholder.info(f"✅ Video is under 59 minutes, no chunking needed")
                    
                return index_video_with_chunking(file_path, index_id, client, status_placeholder, False)
                
            if status_placeholder:
                status_placeholder.info(f"""
                🔪 Video length ({duration/60:.1f} min) exceeds Pegasus limit (59 min)
                🔄 Chunking video into smaller segments...
                """)
            
            chunks_dir = os.path.join(os.path.dirname(file_path), "chunks")
            
            chunk_paths = chunk_video(file_path, chunks_dir, max_duration, status_placeholder)
            
            if not chunk_paths:
                return False, "Failed to chunk video"
                
            if status_placeholder:
                status_placeholder.info(f"📊 Chunking complete - Created {len(chunk_paths)} chunks")
                master_progress = status_placeholder.progress(0)
            
            success_count = 0
            failure_count = 0
            video_ids = []
            
            for i, chunk_path in enumerate(chunk_paths):
                if status_placeholder:
                    status_placeholder.info(f"🎥 Indexing chunk {i+1}/{len(chunk_paths)}")
                    chunk_progress = status_placeholder.progress(0)
                
                try:
                    chunk_task = client.task.create(
                        index_id=index_id,
                        file=chunk_path,
                    )
                    
                    chunk_start_time = time.time()
                    
                    def on_chunk_update(task):
                        elapsed_time = int(time.time() - chunk_start_time)
                        if task.status == "processing" and status_placeholder:
                            progress = min(0.95, elapsed_time / 180)
                            if 'chunk_progress' in locals():
                                chunk_progress.progress(progress)
                            if 'master_progress' in locals():
                                master_value = (i + progress) / len(chunk_paths)
                                master_progress.progress(master_value)
                            status_placeholder.info(f"""
                            🎥 Indexing chunk {i+1}/{len(chunk_paths)}
                            ⏳ Status: {task.status}
                            ⌛ Time elapsed: {elapsed_time} seconds
                            """)
                        elif task.status != "processing" and status_placeholder:
                            status_placeholder.info(f"""
                            🎥 Indexing chunk {i+1}/{len(chunk_paths)}
                            ⏳ Status: {task.status}
                            ⌛ Time elapsed: {elapsed_time} seconds
                            """)
                    
                    chunk_task.wait_for_done(sleep_interval=5, callback=on_chunk_update)
                    
                    if status_placeholder and 'chunk_progress' in locals():
                        chunk_progress.progress(1.0)
                    
                    if status_placeholder and 'master_progress' in locals():
                        master_value = (i + 1) / len(chunk_paths)
                        master_progress.progress(master_value)
                    
                    if chunk_task.status == "ready":
                        success_count += 1
                        video_ids.append(chunk_task.video_id)
                        if status_placeholder:
                            status_placeholder.success(f"✅ Successfully indexed chunk {i+1}/{len(chunk_paths)}")
                    else:
                        failure_count += 1
                        if status_placeholder:
                            status_placeholder.error(f"❌ Failed to index chunk {i+1}/{len(chunk_paths)}")
                        
                    if os.path.exists(chunk_path):
                        os.remove(chunk_path)
                        
                except Exception as e:
                    failure_count += 1
                    if status_placeholder:
                        status_placeholder.error(f"❌ Error indexing chunk {i+1}/{len(chunk_paths)}: {str(e)}")
                    
                    if os.path.exists(chunk_path):
                        os.remove(chunk_path)
            
            try:
                if os.path.exists(chunks_dir):
                    shutil.rmtree(chunks_dir)
            except:
                pass
                
            delete_file(file_path)
            
            if 'indexed_count' in st.session_state:
                st.session_state.indexed_count += success_count
            
            if success_count > 0:
                if status_placeholder:
                    status_placeholder.success(f"✅ Successfully indexed {success_count}/{len(chunk_paths)} chunks")
                return True, f"Successfully indexed {success_count}/{len(chunk_paths)} video chunks"
            else:
                if status_placeholder:
                    status_placeholder.error(f"❌ Failed to index any chunks")
                return False, "Failed to index any video chunks"
            
    except Exception as e:
        if status_placeholder:
            status_placeholder.error(f"❌ Error: {str(e)}")
        return False, str(e)

def process_videos(video_info, download_status, indexing_status):
    try:
        client = TwelveLabs(api_key=st.session_state.api_key)
        downloads_dir = get_downloads_folder()
        st.info(f"📂 Videos will be saved to: {downloads_dir}")

        # Downloading the videos first with simple threading
        downloaded_files = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_url = {}
            for i, info in enumerate(video_info):
                if isinstance(info, dict) and 'url' in info:
                    future = executor.submit(download_video, info['url'])
                    future_to_url[future] = (i, info)
            
            for future in concurrent.futures.as_completed(future_to_url):
                i, info = future_to_url[future]
                try:
                    filename, title = future.result()
                    if filename and os.path.exists(filename):
                        st.success(f"✅ Downloaded: {title}")
                        downloaded_files.append((filename, title))
                    else:
                        st.error(f"Download failed: {title}")
                except Exception as e:
                    st.error(f"Download error: {str(e)}")

        # Check if chunking is needed for Pegasus
        needs_chunking = st.session_state.need_chunking_for_pegasus
        successful_indexes = 0
        
        for filename, title in downloaded_files:
            try:
                success, result = index_video_with_chunking(
                    file_path=filename,
                    index_id=st.session_state.index.id,
                    client=client,
                    status_placeholder=indexing_status,
                    needs_chunking=needs_chunking
                )
                
                if success:
                    successful_indexes += 1
                    st.success(f"✅ Indexed: {title}")
                else:
                    st.error(f"Failed to index: {title} - {result}")
                    
            except Exception as e:
                st.error(f"Indexing error for {title}: {str(e)}")

        st.success(f"✅ Complete: {successful_indexes}/{len(downloaded_files)} videos indexed")
        return True

    except Exception as e:
        st.error(f"Error: {str(e)}")
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
            "10_popular": "10 Most Viewed Videos"
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



def initial_setup():
    st.title("Index UGC with Twelve Labs")
    
    api_key = st.text_input(
        "Enter your Twelve Labs API Key:",
        value="", 
        type="password",
        help="Your API key from the Twelve Labs dashboard"
    )
    
    index_name = st.text_input(
        "Enter Index Name:",
        help="Choose a unique name for your video index"
    )

    st.subheader("Model Selection")
    st.info("Select the models you want to use for indexing.")
    

    col1, col2 = st.columns(2)
    
    with col1:
        use_marengo = st.checkbox("Marengo 2.7", value=True, 
                                help="Marengo 2.7 provides advanced visual and audio understanding capabilities")
        
        marengo_options = []
        if use_marengo:
            st.markdown("#### Marengo Options")
            marengo_visual = st.checkbox("Visual", value=True, key="marengo_visual")
            marengo_audio = st.checkbox("Audio", value=True, key="marengo_audio")
            if marengo_visual:
                marengo_options.append("visual")
            if marengo_audio:
                marengo_options.append("audio")
    
    with col2:
        use_pegasus = st.checkbox("Pegasus 1.2", value=False,
                                help="Pegasus 1.2 enhances indexing with additional visual features and audio capabilities")
        
        pegasus_options = []
        if use_pegasus:
            st.markdown("#### Pegasus Options")
            pegasus_visual = st.checkbox("Visual", value=True, key="pegasus_visual")
            pegasus_audio = st.checkbox("Audio", value=True, key="pegasus_audio")
            if pegasus_visual:
                pegasus_options.append("visual")
            if pegasus_audio:
                pegasus_options.append("audio")
            
            st.info("⚠️ Note: Pegasus model has a 59-minute limit for videos. Longer videos will be automatically chunked.")
    

    st.subheader("Addon Selection")
    use_thumbnail = st.checkbox("Thumbnail", value=True, help="Generate thumbnails for indexed videos")
    
    addons = []
    if use_thumbnail:
        addons.append("thumbnail")
    
    if st.button("Initialize Application"):
        if not api_key:
            st.error("⚠️ Please enter your API key")
            return
        if not index_name:
            st.error("⚠️ Please enter an index name")
            return
        if not use_marengo and not use_pegasus:
            st.error("⚠️ Please select at least one model")
            return
        if use_marengo and not marengo_options:
            st.error("⚠️ Please select at least one option for Marengo")
            return
        if use_pegasus and not pegasus_options:
            st.error("⚠️ Please select at least one option for Pegasus")
            return
            
        try:
            with st.spinner("Setting up your index..."):
                client = TwelveLabs(api_key=api_key)
                
                models = []
                
                if use_marengo:
                    models.append({
                        "name": "marengo2.7",
                        "options": marengo_options
                    })
                
                if use_pegasus:
                    models.append({
                        "name": "pegasus1.2",
                        "options": pegasus_options
                    })
                    # Set flag to enable chunking for Pegasus
                    st.session_state.need_chunking_for_pegasus = True
                else:
                    st.session_state.need_chunking_for_pegasus = False
                
                index = client.index.create(
                    name=index_name,
                    models=models,
                    addons=addons
                )
                
                st.session_state.api_key = api_key
                st.session_state.index = index
                st.session_state.setup_complete = True
                
                model_details = []
                for model in models:
                    model_details.append(f"{model['name']} ({', '.join(model['options'])})")
                
                st.success(f"""
                ✅ Setup completed successfully!
                📊 Active Models: {' and '.join(model_details)}
                {'🖼️ Thumbnail addon enabled' if 'thumbnail' in addons else ''}
                """)
                time.sleep(1)
                st.rerun()
                
        except Exception as e:
            st.error(f"❌ Setup failed: {str(e)}")



def main():
    if not st.session_state.setup_complete or not st.session_state.index:
        initial_setup()
        return
    
    st.title("Index UGC with Twelve Labs")
    
    with st.sidebar:
        st.success(f"✅ Active Index: {st.session_state.index.name}")
        if st.button("Create New Index"):
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
