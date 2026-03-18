// Element Picker - Visual element selection for setup wizard

let isPickerActive = false;
let pickerMode = null; // 'question', 'answers', 'submit'
let hoveredElement = null;
let overlay = null;

// Listen for picker activation
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'startPicker') {
    startPicker(request.mode);
    sendResponse({ success: true });
  } else if (request.action === 'stopPicker') {
    stopPicker();
    sendResponse({ success: true });
  }
  return true;
});

function startPicker(mode) {
  if (isPickerActive) return;

  isPickerActive = true;
  pickerMode = mode;

  // Create overlay
  createOverlay();

  // Add event listeners
  document.addEventListener('mouseover', handleMouseOver, true);
  document.addEventListener('mouseout', handleMouseOut, true);
  document.addEventListener('click', handleClick, true);
  document.addEventListener('keydown', handleKeyDown, true);

  console.log(`Element picker started for: ${mode}`);
}

function stopPicker() {
  if (!isPickerActive) return;

  isPickerActive = false;
  pickerMode = null;
  hoveredElement = null;

  // Remove overlay
  if (overlay) {
    overlay.remove();
    overlay = null;
  }

  // Remove highlight
  removeHighlight();

  // Remove event listeners
  document.removeEventListener('mouseover', handleMouseOver, true);
  document.removeEventListener('mouseout', handleMouseOut, true);
  document.removeEventListener('click', handleClick, true);
  document.removeEventListener('keydown', handleKeyDown, true);

  console.log('Element picker stopped');
}

function createOverlay() {
  overlay = document.createElement('div');
  overlay.id = 'studyflow-picker-overlay';
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.3);
    z-index: 999998;
    pointer-events: none;
  `;

  const banner = document.createElement('div');
  banner.style.cssText = `
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: linear-gradient(135deg, #667eea, #764ba2);
    color: white;
    padding: 16px 32px;
    border-radius: 50px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 16px;
    font-weight: 700;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    z-index: 999999;
    pointer-events: auto;
    display: flex;
    align-items: center;
    gap: 12px;
  `;

  const modeText = {
    'question': '📝 Click on the question text',
    'answers': '☑️ Click on the answer options container',
    'submit': '▶️ Click on the submit button'
  };

  banner.innerHTML = `
    <span>${modeText[pickerMode] || 'Click an element'}</span>
    <button style="
      background: rgba(255, 255, 255, 0.2);
      border: none;
      color: white;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
    " onclick="this.parentElement.parentElement.remove()">ESC to Cancel</button>
  `;

  overlay.appendChild(banner);
  document.body.appendChild(overlay);
}

function handleMouseOver(e) {
  if (!isPickerActive) return;
  if (e.target.id === 'studyflow-picker-overlay' || e.target.closest('#studyflow-picker-overlay')) return;

  e.stopPropagation();
  hoveredElement = e.target;
  highlightElement(hoveredElement);
}

function handleMouseOut(e) {
  if (!isPickerActive) return;
  e.stopPropagation();
}

function handleClick(e) {
  if (!isPickerActive) return;
  if (e.target.id === 'studyflow-picker-overlay' || e.target.closest('#studyflow-picker-overlay')) return;

  e.preventDefault();
  e.stopPropagation();

  const element = hoveredElement;
  if (!element) return;

  // Get element selector
  const selector = getElementSelector(element);
  const preview = element.textContent.trim().substring(0, 100);

  console.log('Selected element:', { selector, preview });

  // Send back to popup
  chrome.runtime.sendMessage({
    action: 'elementSelected',
    mode: pickerMode,
    selector: selector,
    preview: preview
  });

  stopPicker();
}

function handleKeyDown(e) {
  if (e.key === 'Escape') {
    stopPicker();
    chrome.runtime.sendMessage({ action: 'pickerCancelled' });
  }
}

function highlightElement(element) {
  removeHighlight();

  const rect = element.getBoundingClientRect();
  const highlight = document.createElement('div');
  highlight.id = 'studyflow-element-highlight';
  highlight.style.cssText = `
    position: fixed;
    top: ${rect.top}px;
    left: ${rect.left}px;
    width: ${rect.width}px;
    height: ${rect.height}px;
    border: 3px solid #00e676;
    background: rgba(0, 230, 118, 0.1);
    border-radius: 8px;
    z-index: 999999;
    pointer-events: none;
    box-shadow: 0 0 0 4px rgba(0, 230, 118, 0.2),
                0 8px 32px rgba(0, 230, 118, 0.3);
    animation: highlightPulse 1.5s infinite;
  `;

  const style = document.createElement('style');
  style.textContent = `
    @keyframes highlightPulse {
      0%, 100% { box-shadow: 0 0 0 4px rgba(0, 230, 118, 0.2), 0 8px 32px rgba(0, 230, 118, 0.3); }
      50% { box-shadow: 0 0 0 8px rgba(0, 230, 118, 0.3), 0 12px 48px rgba(0, 230, 118, 0.5); }
    }
  `;
  document.head.appendChild(style);

  document.body.appendChild(highlight);
}

function removeHighlight() {
  const existing = document.getElementById('studyflow-element-highlight');
  if (existing) existing.remove();
}

function getElementSelector(element) {
  // Try to get a unique selector
  if (element.id) {
    return `#${element.id}`;
  }

  // Try class name
  if (element.className && typeof element.className === 'string') {
    const classes = element.className.trim().split(/\s+/).filter(c => c);
    if (classes.length > 0) {
      return `.${classes[0]}`;
    }
  }

  // Try tag name with parent context
  const tag = element.tagName.toLowerCase();
  const parent = element.parentElement;
  if (parent && parent.id) {
    return `#${parent.id} > ${tag}`;
  }

  return tag;
}

console.log('StudyFlowSuite element picker loaded');
