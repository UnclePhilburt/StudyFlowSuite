// Content script - runs on every webpage to detect quiz questions
console.log('StudyFlowSuite loaded');

// Track answered questions on one-page quizzes
let answeredQuestions = new Set();

// Detect one-page quiz (all questions visible at once)
function detectOnePageQuiz() {
  console.log('🔍 Scanning for unanswered question in one-page quiz...');

  // Find all question containers
  const questionContainers = document.querySelectorAll('.question, [class*="question"]');

  for (const container of questionContainers) {
    // Skip if container is not visible
    if (container.offsetParent === null || container.offsetHeight === 0 || container.offsetWidth === 0) {
      console.log('⏭️ Skipping hidden question container');
      continue;
    }

    // Create a unique question ID
    const questionId = container.getAttribute('data-question-id') || container.textContent.substring(0, 100);

    // Skip if we've already processed this question in this session
    if (answeredQuestions.has(questionId)) {
      console.log('⏭️ Skipping already answered question');
      continue;
    }

    // Find the question text within this container
    const questionTextElement = container.querySelector('.question_text, .question-text, .questionText, .qtext, [class*="question_text"]');
    let questionText = '';

    if (questionTextElement) {
      questionText = questionTextElement.textContent.trim();
    } else {
      // Fallback: try to find the question text from common patterns
      const fallbackElement = container.querySelector('strong, b, h3, h4, h5, p');
      if (fallbackElement) {
        questionText = fallbackElement.textContent.trim();
      } else {
        // Last resort: get first substantial text from container
        questionText = container.textContent.trim().split('\n').find(line => line.length > 10) || '';
      }
    }

    if (!questionText || questionText.length < 10) continue;

    // Check if it's an essay/text question
    const textInputs = container.querySelectorAll('textarea, input[type="text"]');
    if (textInputs.length > 0) {
      for (const field of textInputs) {
        if (field.offsetParent !== null) {
          // Skip if field already has a value (don't add to answeredQuestions - just skip this field)
          if (field.value.trim() !== '') {
            console.log('⏭️ Text field already filled, skipping without tracking');
            continue; // Skip to next field
          }

          // Found unanswered text question
          console.log('✅ Found unanswered TEXT question:', questionText.substring(0, 100));

          // Mark the field with a unique identifier
          const fieldId = `studyflow-field-${Date.now()}`;
          field.setAttribute('data-studyflow-field-id', fieldId);

          // Mark as answered (will be filled)
          container.setAttribute('data-question-id', questionId);
          answeredQuestions.add(questionId);

          return {
            question: questionText,
            answers: [],
            found: true,
            isEssay: true,
            essayFieldId: fieldId,
            questionElement: container,
            debug: ['One-page quiz: text question']
          };
        }
      }
    }

    // Check if it's a multiple choice question
    const radioInputs = container.querySelectorAll('input[type="radio"], input[type="checkbox"]');
    if (radioInputs.length > 0) {
      // Check if any answer is already selected (don't add to answeredQuestions - just skip this question)
      const isAnswered = Array.from(radioInputs).some(input => input.checked);
      if (isAnswered) {
        console.log('⏭️ Radio button already checked, skipping without tracking');
        continue;
      }

      // Found unanswered multiple choice question
      console.log('✅ Found unanswered MULTIPLE CHOICE question:', questionText.substring(0, 100));

      const answers = [];
      const radioGroupId = `studyflow-radio-${Date.now()}`;

      radioInputs.forEach((input, index) => {
        // Mark each input with a unique group identifier
        input.setAttribute('data-studyflow-radio-group', radioGroupId);
        input.setAttribute('data-studyflow-radio-index', index);

        // Find label text
        let answerText = '';
        if (input.id) {
          const label = container.querySelector(`label[for="${input.id}"]`);
          if (label) answerText = label.textContent.trim();
        }
        if (!answerText) {
          const parentLabel = input.closest('label');
          if (parentLabel) answerText = parentLabel.textContent.trim();
        }
        if (!answerText && input.nextSibling) {
          answerText = input.nextSibling.textContent?.trim() || '';
        }
        if (!answerText) {
          const parent = input.parentElement;
          if (parent) answerText = parent.textContent.trim();
        }

        answerText = answerText.replace(/\s+/g, ' ').trim();

        if (answerText && answerText.length > 0) {
          answers.push({
            index: index + 1,
            text: answerText,
            element: input,
            type: input.type
          });
        }
      });

      // Mark as answered (will be clicked)
      container.setAttribute('data-question-id', questionId);
      answeredQuestions.add(questionId);

      return {
        question: questionText,
        answers: answers,
        found: true,
        isEssay: false,
        radioGroupId: radioGroupId,
        questionElement: container,
        debug: ['One-page quiz: multiple choice']
      };
    }
  }

  // No more unanswered questions found
  console.log('✅ All questions answered!');
  return {
    question: null,
    answers: [],
    found: false,
    debug: ['One-page quiz: all questions completed']
  };
}

// Detect quiz questions on the page
function detectQuiz() {
  const quizData = {
    question: null,
    answers: [],
    found: false,
    debug: [],
    isEssay: false,
    essayField: null,
    questionElement: null // Store reference to question element
  };

  console.log('=== QUIZ DETECTION DEBUG ===');

  // Look for any text that might be a question (very broad search)
  const allText = document.body.innerText;
  console.log('Page text length:', allText.length);

  // Common quiz patterns to look for (includes Canvas, Blackboard, Moodle, etc.)
  const questionSelectors = [
    // Canvas LMS
    '.question_text',
    '.quiz_question',
    '[class*="question_text"]',
    // Blackboard
    '.questionText',
    '.vtbegenerated',
    // Moodle
    '.qtext',
    '.formulation',
    // Generic
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    '[class*="question"]',
    '[id*="question"]',
    '[role="heading"]',
    'p strong',
    'p b',
    'div strong',
    'div b',
    '.quiz-question',
    '.question-text',
    'label',
    'p',
    'div'
  ];

  // Find the question - be very lenient
  for (const selector of questionSelectors) {
    const elements = document.querySelectorAll(selector);
    console.log(`Checking selector "${selector}": found ${elements.length} elements`);

    for (const el of elements) {
      const text = el.textContent.trim();

      // Skip if it looks like a page title (contains "Practice Test", "Certification", etc.)
      const isPageTitle = /practice\s+test|certification|exam\s+title|test\s+name/i.test(text);
      if (isPageTitle) {
        console.log(`Skipping page title: ${text.substring(0, 50)}`);
        continue;
      }

      // Very lenient - any text with a question mark or longer than 50 chars with keywords
      const hasQuestionMark = text.includes('?');
      const hasKeywords = /\b(which|what|who|when|where|why|how|select|choose|assessment|monitoring|noted|nurse|patient|client|infant|newborn|should|would|could|teaching)\b/i.test(text);
      const isLongEnough = text.length > 30 && text.length < 2000;

      if ((hasQuestionMark || (hasKeywords && isLongEnough)) && text.length > 20) {
        quizData.question = text;
        quizData.found = true;
        quizData.debug.push(`Found question via selector: ${selector}`);
        console.log('✅ Found question:', text.substring(0, 100));
        break;
      }
    }
    if (quizData.found) break;
  }

  // If still not found, look for ANY paragraph with substantial text
  if (!quizData.found) {
    console.log('Trying fallback: looking for any long paragraph...');
    const allParagraphs = document.querySelectorAll('p, div');
    for (const el of allParagraphs) {
      const text = el.textContent.trim();
      if (text.length > 50 && text.length < 2000 && !text.includes('cookie') && !text.includes('privacy')) {
        quizData.question = text;
        quizData.found = true;
        quizData.debug.push('Found question via fallback (long paragraph)');
        console.log('✅ Found question (fallback):', text.substring(0, 100));
        break;
      }
    }
  }

  // Check for essay/fill-in-the-blank question (textarea, text input, or contenteditable)
  const essayFields = document.querySelectorAll('textarea, input[type="text"], input:not([type="radio"]):not([type="checkbox"]):not([type="button"]):not([type="submit"]), div[contenteditable="true"]');

  if (essayFields.length > 0 && quizData.found) {
    console.log(`Found ${essayFields.length} text input fields`);
    // Check if the text field is visible and not a search/filter field
    for (const field of essayFields) {
      // Only consider visible fields
      if (field.offsetParent !== null) {
        // Skip tiny fields (likely search boxes, filters, etc.)
        if (field.offsetWidth < 100 && field.tagName !== 'TEXTAREA') continue;

        // Skip fields that look like search/navigation
        const fieldText = (field.placeholder || field.name || field.id || '').toLowerCase();
        if (fieldText.includes('search') || fieldText.includes('filter') || fieldText.includes('find')) continue;

        // Mark the field with a unique identifier
        const fieldId = `studyflow-field-${Date.now()}`;
        field.setAttribute('data-studyflow-field-id', fieldId);

        quizData.isEssay = true;
        quizData.essayFieldId = fieldId;

        // Determine if it's fill-in-the-blank (short) or essay (long)
        const isFillInBlank = field.tagName === 'INPUT' && field.offsetHeight < 100;
        console.log(isFillInBlank ? '✅ Detected as FILL-IN-THE-BLANK question' : '✅ Detected as ESSAY question');
        quizData.debug.push(isFillInBlank ? 'Detected fill-in-the-blank question' : 'Detected essay question with text input field');
        return quizData; // Return early, no need to look for multiple choice
      }
    }
  }

  // Find answer options (radio buttons, checkboxes, or text options)
  let answerInputs = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
  console.log(`Found ${answerInputs.length} radio/checkbox inputs`);

  // If no inputs found, the quiz might use clickable divs instead
  if (answerInputs.length === 0) {
    console.log('No radio buttons found, looking for clickable answer divs...');
    // We'll still return found=false if we can't find clickable answers
    // But at least we tried
  }

  answerInputs.forEach((input, index) => {
    // Find associated label or nearby text
    let answerText = '';

    // Try to find label by 'for' attribute
    if (input.id) {
      const label = document.querySelector(`label[for="${input.id}"]`);
      if (label) {
        answerText = label.textContent.trim();
      }
    }

    // Try parent label
    if (!answerText) {
      const parentLabel = input.closest('label');
      if (parentLabel) {
        answerText = parentLabel.textContent.trim();
      }
    }

    // Try next sibling
    if (!answerText && input.nextSibling) {
      answerText = input.nextSibling.textContent?.trim() || '';
    }

    // Try parent div text
    if (!answerText) {
      const parent = input.parentElement;
      if (parent) {
        answerText = parent.textContent.trim();
      }
    }

    // Clean up answer text (remove extra whitespace)
    answerText = answerText.replace(/\s+/g, ' ').trim();

    if (answerText && answerText.length > 0) {
      quizData.answers.push({
        index: index + 1,
        text: answerText,
        element: input,
        type: input.type
      });
      console.log(`✅ Answer ${index + 1}:`, answerText.substring(0, 50));
      quizData.debug.push(`Found answer ${index + 1}: ${answerText.substring(0, 30)}...`);
    }
  });

  console.log(`Total answers found: ${quizData.answers.length}`);

  return quizData;
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'detectQuiz') {
    // Check if one-page mode is enabled
    const onePageMode = request.onePageMode || false;

    if (onePageMode) {
      console.log('📄 ONE-PAGE MODE enabled');
      const quizData = detectOnePageQuiz();
      sendResponse(quizData);
    } else {
      console.log('📄 SEQUENTIAL MODE (default)');
      const quizData = detectQuiz();
      sendResponse(quizData);
    }
  } else if (request.action === 'resetAnsweredQuestions') {
    // Reset tracking when quiz starts
    answeredQuestions.clear();
    console.log('🔄 Reset answered questions tracker');
    sendResponse({ success: true });
  } else if (request.action === 'clickAnswer') {
    const answerIndex = request.answerIndex;
    const radioGroupId = request.radioGroupId;

    let input;
    if (radioGroupId) {
      // One-page mode: find the specific radio button by group ID and index
      input = document.querySelector(`[data-studyflow-radio-group="${radioGroupId}"][data-studyflow-radio-index="${answerIndex - 1}"]`);
    } else {
      // Sequential mode: use all radio buttons on page
      const inputs = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
      input = inputs[answerIndex - 1];
    }

    if (input) {
      // Scroll into view
      input.scrollIntoView({ behavior: 'smooth', block: 'center' });

      // Wait a bit then click
      setTimeout(() => {
        input.click();

        // Highlight the answer briefly
        const parent = input.closest('label') || input.parentElement;
        if (parent) {
          parent.style.backgroundColor = '#90EE90';
          parent.style.transition = 'background-color 0.3s';
          setTimeout(() => {
            parent.style.backgroundColor = '';
          }, 2000);
        }

        sendResponse({ success: true });
      }, 500);
    } else {
      console.error('Radio button not found. answerIndex:', answerIndex, 'radioGroupId:', radioGroupId);
      sendResponse({ success: false, error: 'Answer not found' });
    }

    return true; // Keep channel open for async response
  } else if (request.action === 'fillEssay') {
    // Fill in essay answer
    const essayAnswer = request.essayAnswer;
    const essayFieldId = request.essayFieldId;

    // Find the specific field by its ID
    const field = document.querySelector(`[data-studyflow-field-id="${essayFieldId}"]`);

    if (field) {
      field.scrollIntoView({ behavior: 'smooth', block: 'center' });

      setTimeout(() => {
        // Set the value
        if (field.tagName === 'TEXTAREA' || field.tagName === 'INPUT') {
          field.value = essayAnswer;
          // Trigger input event so the page knows the value changed
          field.dispatchEvent(new Event('input', { bubbles: true }));
          field.dispatchEvent(new Event('change', { bubbles: true }));
        } else if (field.contentEditable === 'true') {
          field.textContent = essayAnswer;
          field.dispatchEvent(new Event('input', { bubbles: true }));
        }

        // Highlight the field briefly
        field.style.backgroundColor = '#90EE90';
        field.style.transition = 'background-color 0.3s';
        setTimeout(() => {
          field.style.backgroundColor = '';
        }, 2000);

        sendResponse({ success: true });
      }, 500);
    } else {
      console.error('Essay field not found with ID:', essayFieldId);
      sendResponse({ success: false, error: 'Essay field not found' });
    }

    return true; // Keep channel open for async response
  } else if (request.action === 'clickSubmit') {
    // Find and click the submit button
    console.log('Looking for submit button...');

    let submitButton = null;

    // First try: button[type="submit"] or input[type="submit"]
    const typeSubmitButtons = document.querySelectorAll('button[type="submit"], input[type="submit"]');
    if (typeSubmitButtons.length > 0) {
      submitButton = typeSubmitButtons[0];
      console.log('Found submit button by type="submit"');
    }

    // Second try: all buttons, search by text
    if (!submitButton) {
      const allButtons = document.querySelectorAll('button, input[type="button"], a.button, a.btn');
      for (const btn of allButtons) {
        const text = (btn.textContent || btn.value || '').toLowerCase().trim();
        console.log(`Checking button text: "${text}"`);

        if (text === 'submit' ||
            text === 'next' ||
            text === 'continue' ||
            text === 'check' ||
            text.includes('submit') ||
            text.includes('next')) {
          submitButton = btn;
          console.log(`✅ Found button by text: "${text}"`);
          break;
        }
      }
    }

    // Third try: any button on the page (last resort)
    if (!submitButton) {
      const anyButtons = document.querySelectorAll('button');
      console.log(`Found ${anyButtons.length} total buttons on page`);

      // Log all button texts for debugging
      anyButtons.forEach((btn, i) => {
        console.log(`Button ${i}: "${btn.textContent.trim()}"`);
      });

      if (anyButtons.length > 0) {
        // Use the first visible button as last resort
        for (const btn of anyButtons) {
          if (btn.offsetParent !== null) { // Check if visible
            submitButton = btn;
            console.log(`Using first visible button: "${btn.textContent.trim()}"`);
            break;
          }
        }
      }
    }

    if (submitButton) {
      submitButton.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setTimeout(() => {
        console.log('Clicking submit button');
        submitButton.click();
        sendResponse({ success: true });
      }, 500);
    } else {
      console.log('❌ No submit button found');
      sendResponse({ success: false, error: 'Submit button not found' });
    }

    return true; // Keep channel open for async response
  } else if (request.action === 'showAlert') {
    // Show alert message to user
    alert(request.message);
    sendResponse({ success: true });
  }
});

// Notify that script is ready
console.log('StudyFlowSuite ready to detect quizzes');
