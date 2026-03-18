// Background service worker - runs the quiz loop independently
const BACKEND_URL = 'https://studyflowsuite.onrender.com';

let isRunning = false;
let isPaused = false;
let waitingForNavigation = false;
let questionCount = 0;
let errorCount = 0;
let lastQuestionText = null;
let sameQuestionCount = 0;
let currentTabId = null;
let latestAnswer = null;

// Quiz settings
let quizSettings = {
  totalQuestions: null,
  targetTime: null, // in minutes
  onePageMode: false,
  aiModel: 'gpt-4o-mini' // default model
};
let quizStartTime = null;

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'start') {
    startQuizMode(request.tabId, request.settings);
    sendResponse({ success: true });
  } else if (request.action === 'stop') {
    stopQuizMode();
    sendResponse({ success: true });
  } else if (request.action === 'getStatus') {
    sendResponse({
      isRunning,
      isPaused,
      waitingForNavigation,
      questionCount,
      errorCount,
      currentQuestion: lastQuestionText?.substring(0, 100),
      latestAnswer
    });
  } else if (request.action === 'resume') {
    // Resume from waiting state
    if (waitingForNavigation) {
      console.log('Resuming from waiting state...');
      waitingForNavigation = false;
      isPaused = false;

      // Reset answered questions for new page
      chrome.tabs.sendMessage(currentTabId, { action: 'resetAnsweredQuestions' });

      sendResponse({ success: true });
    } else {
      sendResponse({ success: false, error: 'Not in waiting state' });
    }
  }
  return true;
});

function startQuizMode(tabId, settings = {}) {
  if (isRunning) return;

  isRunning = true;
  isPaused = false;
  waitingForNavigation = false;
  currentTabId = tabId;
  questionCount = 0;
  errorCount = 0;
  lastQuestionText = null;
  sameQuestionCount = 0;
  quizSettings = settings;
  quizStartTime = Date.now();

  console.log('Starting quiz mode on tab:', tabId);
  console.log('Quiz settings:', quizSettings);
  updateBadge('▶', '#00c853');

  // Reset answered questions tracker in content script
  chrome.tabs.sendMessage(tabId, { action: 'resetAnsweredQuestions' });

  runQuizLoop();
}

function stopQuizMode() {
  isRunning = false;
  isPaused = false;
  waitingForNavigation = false;
  currentTabId = null;
  quizSettings = { totalQuestions: null, targetTime: null, onePageMode: false, aiModel: 'gpt-4o-mini' };
  quizStartTime = null;
  console.log('Quiz mode stopped');
  updateBadge('', '');
}

async function runQuizLoop() {
  while (isRunning) {
    try {
      // If waiting for user to navigate, pause the loop
      if (waitingForNavigation) {
        updateBadge('⏸', '#ffc107');
        await sleep(1000);
        continue;
      }

      // Detect quiz on current tab
      const quiz = await new Promise((resolve) => {
        chrome.tabs.sendMessage(currentTabId, {
          action: 'detectQuiz',
          onePageMode: quizSettings.onePageMode
        }, (response) => {
          if (chrome.runtime.lastError) {
            console.error('Error:', chrome.runtime.lastError);
            resolve(null);
          } else {
            resolve(response);
          }
        });
      });

      if (!quiz || !quiz.found) {
        // Check if this is the end of a one-page quiz
        if (quiz && quiz.debug && quiz.debug.includes('One-page quiz: all questions completed')) {
          console.log('✅ All questions on this page completed!');

          // Pause and wait for user to navigate
          console.log('⏸ Waiting for user to navigate to next page...');
          waitingForNavigation = true;
          isPaused = true;
          updateBadge('⏸', '#ffc107');

          // Wait in the loop for user to click resume
          continue;
        }

        console.log('No quiz found, waiting...');
        await sleep(2000);
        continue;
      }

      // Check if one-page mode is enabled
      const isOnePageQuiz = quizSettings.onePageMode;

      // Check if it's an essay question
      if (quiz.isEssay) {
        console.log('📝 Essay question detected - writing AI answer...');

        // Get essay answer from AI
        const essayAnswer = await getEssayAnswer(quiz.question);
        console.log('AI Essay Answer:', essayAnswer.substring(0, 100));

        // Fill in the essay field
        await new Promise((resolve) => {
          chrome.tabs.sendMessage(currentTabId, {
            action: 'fillEssay',
            essayAnswer: essayAnswer,
            essayFieldId: quiz.essayFieldId
          }, (response) => {
            if (chrome.runtime.lastError) {
              console.error('Error filling essay:', chrome.runtime.lastError);
            }
            resolve(response);
          });
        });

        await sleep(1500);

        // Only click submit if NOT a one-page quiz
        if (!isOnePageQuiz) {
          await new Promise((resolve) => {
            chrome.tabs.sendMessage(currentTabId, { action: 'clickSubmit' }, (response) => {
              if (chrome.runtime.lastError) {
                console.error('Error clicking submit:', chrome.runtime.lastError);
              }
              resolve(response);
            });
          });
        }

        questionCount++;
        console.log(`✅ Essay question ${questionCount} completed`);
        updateBadge(questionCount.toString(), '#00c853');

        // Check if we've hit the total questions limit
        if (quizSettings.totalQuestions && questionCount >= quizSettings.totalQuestions) {
          console.log('🎉 Reached total questions limit. Stopping quiz.');

          // If one-page quiz, click submit now
          if (isOnePageQuiz) {
            await new Promise((resolve) => {
              chrome.tabs.sendMessage(currentTabId, { action: 'clickSubmit' }, resolve);
            });
          }

          stopQuizMode();
          break;
        }

        // Use smart delay
        const delay = calculateSmartDelay();
        await sleep(delay);
        continue; // Skip the multiple choice logic below
      }

      // Check if same question
      const currentQuestionText = quiz.question.substring(0, 200);
      if (currentQuestionText === lastQuestionText) {
        sameQuestionCount++;
        console.log(`⚠️ Same question detected (count: ${sameQuestionCount}) - question may already be answered or page not changed`);

        if (sameQuestionCount > 5) {
          console.log('⚠️ Stuck on same question after 5 attempts - stopping quiz');
          errorCount++;
          updateBadge('⚠️', '#f44336');
          stopQuizMode();
          break;
        }

        await sleep(2000);
        continue;
      }

      // New question!
      sameQuestionCount = 0;
      lastQuestionText = currentQuestionText;
      console.log('✅ New question detected:', currentQuestionText.substring(0, 50));

      // Get AI answer
      const answer = await getAIAnswer(quiz);
      console.log('AI Answer:', answer.correct_index);

      // Clean the question text (remove common headers)
      let cleanQuestion = quiz.question;
      const headerPatterns = [
        /^.*?Practice Test\s*/i,
        /^.*?Certification\s*/i,
        /^.*?Exam\s*/i,
        /^Question\s+\d+\s*/i,
        /^\d+\.\s*/,
        /^Q\d+[\s:]+/i
      ];

      for (const pattern of headerPatterns) {
        cleanQuestion = cleanQuestion.replace(pattern, '');
      }
      cleanQuestion = cleanQuestion.trim();

      // Store latest answer for history (with unique ID to prevent duplicates)
      const answerText = quiz.answers[answer.correct_index - 1]?.text || `Answer #${answer.correct_index}`;
      latestAnswer = {
        id: `${Date.now()}-${currentQuestionText.substring(0, 50)}`, // Unique ID
        question: cleanQuestion,
        answer: answerText,
        reasoning: answer.reasoning,
        timestamp: Date.now()
      };

      // Click answer
      await new Promise((resolve) => {
        chrome.tabs.sendMessage(currentTabId, {
          action: 'clickAnswer',
          answerIndex: answer.correct_index,
          radioGroupId: quiz.radioGroupId
        }, (response) => {
          if (chrome.runtime.lastError) {
            console.error('Error clicking answer:', chrome.runtime.lastError);
          }
          resolve(response);
        });
      });

      await sleep(1500);

      // Only click submit if NOT a one-page quiz
      if (!isOnePageQuiz) {
        await new Promise((resolve) => {
          chrome.tabs.sendMessage(currentTabId, { action: 'clickSubmit' }, (response) => {
            if (chrome.runtime.lastError) {
              console.error('Error clicking submit:', chrome.runtime.lastError);
            }
            resolve(response);
          });
        });
      }

      questionCount++;
      console.log(`✅ Question ${questionCount} completed`);
      updateBadge(questionCount.toString(), '#00c853');

      // Check if we've hit the total questions limit
      if (quizSettings.totalQuestions && questionCount >= quizSettings.totalQuestions) {
        console.log('🎉 Reached total questions limit. Stopping quiz.');

        // If one-page quiz, click submit now
        if (isOnePageQuiz) {
          await new Promise((resolve) => {
            chrome.tabs.sendMessage(currentTabId, { action: 'clickSubmit' }, (response) => {
              if (chrome.runtime.lastError) {
                console.error('Error clicking submit:', chrome.runtime.lastError);
              }
              resolve(response);
            });
          });
        }

        stopQuizMode();
        break;
      }

      // Use smart delay based on target time
      const delay = calculateSmartDelay();
      await sleep(delay);

    } catch (error) {
      console.error('❌ Error in quiz loop:', error);
      console.error('Error details:', error.message);
      console.error('Stack trace:', error.stack);
      errorCount++;

      // If API failed, skip this question and move on
      if (error.message && error.message.includes('Failed to get AI answer')) {
        console.log('⏭️ Skipping question due to API failure - clicking submit to move on');
        lastQuestionText = null; // Reset so we don't get stuck

        // Click submit to move to next question
        try {
          await new Promise((resolve) => {
            chrome.tabs.sendMessage(currentTabId, { action: 'clickSubmit' }, (response) => {
              if (chrome.runtime.lastError) {
                console.error('Error clicking submit:', chrome.runtime.lastError);
              }
              resolve(response);
            });
          });
          await sleep(2000);
        } catch (e) {
          console.error('Failed to click submit:', e);
        }
      }

      updateBadge('❌', '#f44336');
      await sleep(3000);
    }
  }

  updateBadge('', '');
}

async function getAIAnswer(quiz) {
  const requestData = {
    question: quiz.question,
    answers: quiz.answers.map(a => a.text),
    model: quizSettings.aiModel || 'gemini-2.5-flash'
  };

  console.log('Sending to API:', requestData);

  const response = await fetch(`${BACKEND_URL}/api/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestData)
  });

  if (!response.ok) {
    const errorText = await response.text();
    console.error('API Error Response:', response.status, errorText);
    throw new Error(`Failed to get AI answer: ${response.status} - ${errorText}`);
  }

  const data = await response.json();
  return {
    correct_index: data.correct_answer_index,
    reasoning: data.reasoning || 'No explanation provided'
  };
}

async function getEssayAnswer(question) {
  const response = await fetch(`${BACKEND_URL}/api/essay`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question: question,
      model: quizSettings.aiModel || 'gpt-4o-mini'
    })
  });

  if (!response.ok) {
    throw new Error('Failed to get AI essay answer');
  }

  const data = await response.json();
  return data.essay_answer || 'No answer generated';
}

function updateBadge(text, color) {
  chrome.action.setBadgeText({ text });
  if (color) {
    chrome.action.setBadgeBackgroundColor({ color });
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Calculate smart delay for next question based on target time
function calculateSmartDelay() {
  // If no target time set, return no delay (0 seconds)
  if (!quizSettings.targetTime || !quizSettings.totalQuestions) {
    return 0;
  }

  const elapsedMinutes = (Date.now() - quizStartTime) / 1000 / 60;
  const remainingMinutes = quizSettings.targetTime - elapsedMinutes;
  const questionsLeft = quizSettings.totalQuestions - questionCount;

  // If we're out of time or done, use minimal delay
  if (remainingMinutes <= 0 || questionsLeft <= 0) {
    return 2000;
  }

  // Calculate average time per question remaining (in milliseconds)
  const avgTimePerQuestion = (remainingMinutes / questionsLeft) * 60 * 1000;

  // Add randomization (±30%) to make it feel more human
  const variation = avgTimePerQuestion * 0.3;
  const randomDelay = avgTimePerQuestion + (Math.random() * variation * 2 - variation);

  // Ensure delay is between 2-30 seconds for realism
  const clampedDelay = Math.max(2000, Math.min(30000, randomDelay));

  console.log(`Smart delay: ${Math.round(clampedDelay / 1000)}s (${questionsLeft} questions left, ${remainingMinutes.toFixed(1)}min remaining)`);

  return clampedDelay;
}

console.log('StudyFlowSuite background worker loaded');
