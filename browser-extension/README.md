# StudyFlow Browser Extension

A Chrome extension for AI-powered quiz assistance for homework and practice.

## Features

- **Automatic Quiz Detection**: Scans webpage for quiz questions and answer options
- **AI-Powered Answers**: Uses GPT-4o to determine correct answers
- **Auto-Click**: Automatically clicks the correct answer and submit button
- **Clean UI**: Simple popup interface

## Installation

1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `browser-extension` folder
5. The extension icon should appear in your toolbar

## Setup

No setup required! The extension uses the StudyFlow backend server which has the API key already configured.

## Usage

1. Navigate to a quiz page
2. Click the extension icon
3. Click "Detect Quiz on Page"
4. Click "Get AI Answer" to see the correct answer
5. Click "Auto-Click Answer" to automatically select and submit

## How It Works

1. **Content Script** (`content.js`): Runs on every webpage, detects quiz HTML elements
2. **Popup UI** (`popup.html/popup.js`): User interface for interacting with the extension
3. **AI Integration**: Sends question to OpenAI GPT-4o for analysis
4. **Auto-Click**: Programmatically clicks radio buttons and submit buttons

## Notes

- Works with most quiz platforms (Google Forms, Canvas, Blackboard, etc.)
- No OCR needed - reads HTML directly
- Much faster and more reliable than desktop vision approach
- Requires your own OpenAI API key

## Privacy

- No API key needed - handled by backend
- Quiz data sent to StudyFlow backend server
- Backend server communicates with OpenAI API
