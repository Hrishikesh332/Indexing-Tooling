<div align="center">
    <h1>Twelve Labs UGC Indexer</h1>
    <p>
        <h> Indexing UGC videos using Twelve Labs AI video understanding platform. This tool enables - downloading, processing, and indexing of videos, making them searchable and analyzable through the Twelve Labs API. </h>
    </p>
</div>



## Overview

This application simplifies the process of indexing YouTube content with Twelve Labs by handling -
- Direct video URL processing
- YouTube channel analysis understanding and then indexing
- Automatic video downloading
- Video chunking for long form content [for pegasus-1.2]


## Prev. Core Architectural Flow (Excluding Chunking) -

![Core Architectural Flow](https://github.com/Hrishikesh332/Indexing-Tooling/blob/main/src/workflow-tooling-indexing.png)

## Features

| Feature | Status | Description |
|---------|--------|-------------|
| ✅ Direct URL Indexing | Implemented | Index videos from direct YouTube URLs |
| ✅ Batch Processing | Implemented | Process up to 5 videos at once |
| ✅ Channel Analysis | Implemented | Extract specific videos from YouTube channels |
| ✅ Multiple Model Support | Implemented | Choose between Marengo 2.7 and Pegasus 1.2 models |
| ✅ Granular ModelParameter Options | Implemented | Customize visual and audio processing options |
| ✅ Video Chunking | Implemented | Automatically chunk videos longer than 59 minutes for Pegasus compatibility |
| ✅ Progress Tracking | Implemented | Track download, chunking, and indexing progress |


## Future Implementations Plan

| Feature | Status | Description |
|---------|--------|-------------|
| 🔄 Chunking for Marengo | Planned | Video Chunking for the Marengo-2.7 model |


## Channel Video Options

| Option | Description |
|--------|-------------|
| 5 Newest Videos | Index the 5 most recently uploaded videos |
| 10 Newest Videos | Index the 10 most recently uploaded videos |
| 10 Oldest Videos | Index the 10 oldest videos from the channel |
| 10 Most Viewed Videos | Index the 10 most popular videos by view count |

## Usage

### Initial Setup
1. Enter your Twelve Labs API key, Do generate the API Key from [Twelve Labs Playground]()
2. Create a new index name.
3. Select the models and options you want to use as per your usecase.

### Indexing Individual Videos
1. Navigate to the "Video URLs" tab.
2. Enter up to 5 YouTube video URLs.
3. Click "Download and Index."

### Processing YouTube Channels
1. Navigate to the "Channel Videos" tab.
2. Enter a YouTube channel URL.
3. Select which videos to process (newest, oldest, or most popular).
4. Click "Fetch Videos" to preview the videos.
5. Click "Process Videos" to download and index them.


## Installation

1. Clone the repository
```bash
git clone https://github.com/Hrishikesh332/Indexing-Tooling.git
```

2. Install the required dependencies
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your API keys
```ini
YOUTUBE_API_KEY=your_youtube_api_key_here
```

4. Run the application
```bash
streamlit run app.py
```


## Contribute

Feedbacks are welcome! Please feel free to submit the feature or bug as a Pull Request.


