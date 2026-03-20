// Element Picker - Visual element selection for setup wizard

let isPickerActive = false;
let pickerMode = null; // 'question', 'answers', 'submit'
let hoveredElement = null;
let overlay = null;

// Dev Inspector (separate from picker)
let isDevInspectorActive = false;
let devHoveredElement = null;

// Listen for picker activation
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'startPicker') {
    startPicker(request.mode);
    sendResponse({ success: true });
  } else if (request.action === 'stopPicker') {
    stopPicker();
    sendResponse({ success: true });
  } else if (request.action === 'startDevInspector') {
    startDevInspector();
    sendResponse({ success: true });
  } else if (request.action === 'stopDevInspector') {
    stopDevInspector();
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

// === DEV INSPECTOR (Development Tool) ===

function startDevInspector() {
  if (isDevInspectorActive) return;

  isDevInspectorActive = true;
  console.log('🔍 Dev Inspector activated');

  // Add event listeners
  document.addEventListener('mouseover', devHandleMouseOver, true);
  document.addEventListener('mouseout', devHandleMouseOut, true);
  document.addEventListener('click', devHandleClick, true);
  document.addEventListener('keydown', devHandleKeyDown, true);

  // Create overlay banner
  const banner = document.createElement('div');
  banner.id = 'studyflow-dev-banner';
  banner.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    background: linear-gradient(135deg, #f59e0b, #dc2626);
    color: white;
    padding: 12px;
    text-align: center;
    font-family: Arial, sans-serif;
    font-size: 14px;
    font-weight: bold;
    z-index: 999999;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  `;
  banner.textContent = '🔍 DEV INSPECTOR ACTIVE - Click elements to log selectors to background console (ESC to exit)';
  document.body.appendChild(banner);
}

function stopDevInspector() {
  if (!isDevInspectorActive) return;

  isDevInspectorActive = false;
  devHoveredElement = null;

  // Remove banner
  const banner = document.getElementById('studyflow-dev-banner');
  if (banner) banner.remove();

  // Remove highlight
  removeHighlight();

  // Remove event listeners
  document.removeEventListener('mouseover', devHandleMouseOver, true);
  document.removeEventListener('mouseout', devHandleMouseOut, true);
  document.removeEventListener('click', devHandleClick, true);
  document.removeEventListener('keydown', devHandleKeyDown, true);

  console.log('🔍 Dev Inspector stopped');
}

function devHandleMouseOver(e) {
  if (!isDevInspectorActive) return;
  if (e.target.id === 'studyflow-dev-banner') return;

  e.stopPropagation();
  devHoveredElement = e.target;
  highlightElement(devHoveredElement);
}

function devHandleMouseOut(e) {
  if (!isDevInspectorActive) return;
  e.stopPropagation();
}

function devHandleClick(e) {
  if (!isDevInspectorActive) return;
  if (e.target.id === 'studyflow-dev-banner') return;

  e.preventDefault();
  e.stopPropagation();

  const element = devHoveredElement;
  if (!element) return;

  // Get comprehensive element info
  const selector = getDetailedSelector(element);
  const textPreview = element.textContent.trim().substring(0, 200);
  const htmlPreview = element.outerHTML.substring(0, 500);

  const elementInfo = {
    tagName: element.tagName,
    id: element.id,
    className: element.className,
    attributes: Array.from(element.attributes).map(attr => ({
      name: attr.name,
      value: attr.value
    })),
    parentTag: element.parentElement?.tagName,
    parentClass: element.parentElement?.className
  };

  // Log to content script console
  console.log('=== DEV INSPECTOR CLICKED ===');
  console.log('Selector:', selector);
  console.log('Element Info:', elementInfo);
  console.log('Text:', textPreview);
  console.log('HTML:', htmlPreview);
  console.log('Element:', element);
  console.log('========================');

  // Send to background for service worker console logging
  chrome.runtime.sendMessage({
    action: 'devInspectorResult',
    selector: selector,
    elementInfo: elementInfo,
    textPreview: textPreview,
    htmlPreview: htmlPreview
  });
}

function devHandleKeyDown(e) {
  if (e.key === 'Escape') {
    stopDevInspector();
  }
}

function getDetailedSelector(element) {
  // Try multiple selector strategies
  const selectors = [];

  // 1. ID
  if (element.id) {
    selectors.push(`#${element.id}`);
  }

  // 2. Class(es)
  if (element.className && typeof element.className === 'string') {
    const classes = element.className.trim().split(/\s+/).filter(c => c);
    if (classes.length > 0) {
      selectors.push(`.${classes.join('.')}`);
      selectors.push(`.${classes[0]}`); // Just first class
    }
  }

  // 3. Data attributes
  Array.from(element.attributes).forEach(attr => {
    if (attr.name.startsWith('data-')) {
      selectors.push(`[${attr.name}="${attr.value}"]`);
    }
  });

  // 4. Tag with parent
  const tag = element.tagName.toLowerCase();
  if (element.parentElement) {
    if (element.parentElement.id) {
      selectors.push(`#${element.parentElement.id} > ${tag}`);
    } else if (element.parentElement.className && typeof element.parentElement.className === 'string') {
      const parentClass = element.parentElement.className.trim().split(/\s+/)[0];
      if (parentClass) {
        selectors.push(`.${parentClass} > ${tag}`);
      }
    }
  }

  // 5. Just the tag
  selectors.push(tag);

  return selectors;
}

console.log('StudyFlowSuite element picker loaded');
