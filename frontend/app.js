'use strict';

/* ------------------------------------------------------------------ */
/* API 클라이언트 — 모든 fetch 호출은 이 객체를 통해서만 이루어진다.    */
/* ------------------------------------------------------------------ */

const API_BASE = '/api';

// 일반 조회 API 타임아웃. 정보나루는 백엔드에서 8초 단일 시도(재시도 0, ADR-0004)라
// 10초면 충분하다.
const API_TIMEOUT_MS = 10000;

// generate 전용 타임아웃. 백엔드 LLM 호출은 15초 × 최대 2회(1차 + 재시도 1회) =
// 최대 30초까지 걸릴 수 있다(llm.py LLM_TIMEOUT/LLM_MAX_ATTEMPTS, ADR-0004).
// 이 값이 30초보다 짧으면 1차 호출이 느릴 때 프론트가 먼저 abort 해서, 재시도가
// 성공해도 사용자는 항상 에러 화면을 보게 된다 — 1계층 폴백이 무력화된다.
// 30초 + 네트워크·렌더 여유 5초 = 35초.
const GENERATE_TIMEOUT_MS = 35000;

// PDF 렌더는 Chromium 기동 포함이라 별도 여유값.
const PDF_TIMEOUT_MS = 30000;

function fetchJson(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const opts = Object.assign({}, options, { signal: controller.signal });

    return fetch(url, opts)
        .then((res) => {
            if (!res.ok) {
                throw new Error('HTTP ' + res.status);
            }
            return res.json();
        })
        .finally(() => clearTimeout(timer));
}

const api = {
    getStories() {
        return fetchJson(API_BASE + '/stories', {}, API_TIMEOUT_MS);
    },
    getStory(id) {
        return fetchJson(API_BASE + '/stories/' + encodeURIComponent(id), {}, API_TIMEOUT_MS);
    },
    generateStory(id, payload) {
        return fetchJson(
            API_BASE + '/stories/' + encodeURIComponent(id) + '/generate',
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            },
            GENERATE_TIMEOUT_MS
        );
    },
    getRecommendations(sessionId) {
        return fetchJson(API_BASE + '/sessions/' + encodeURIComponent(sessionId) + '/recommendations', {}, API_TIMEOUT_MS);
    },
    // 아이 이름은 URL(쿼리스트링)이 아니라 POST 바디로만 보낸다 — 서버 액세스 로그·
    // 브라우저 히스토리에 이름이 남지 않게 하기 위함(NFR-6 / ADR-0005).
    fetchPdfBlob(sessionId, authorName) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), PDF_TIMEOUT_MS);

        return fetch(API_BASE + '/sessions/' + encodeURIComponent(sessionId) + '/pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ author_name: authorName }),
            signal: controller.signal
        })
            .then((res) => {
                if (!res.ok) {
                    throw new Error('HTTP ' + res.status);
                }
                return res.blob();
            })
            .finally(() => clearTimeout(timer));
    }
};

/* ------------------------------------------------------------------ */
/* 상태                                                                */
/* ------------------------------------------------------------------ */

const state = {
    lang: 'ko',
    stories: [],
    currentStory: null,
    sessionId: null,
    pages: [],
    keywords: [],
    recognizing: false,
    finalTranscript: ''
};

/* ------------------------------------------------------------------ */
/* DOM 캐시 (init에서 채움)                                            */
/* ------------------------------------------------------------------ */

let el = {};
let recognition = null;

/* ------------------------------------------------------------------ */
/* 화면 전환                                                           */
/* ------------------------------------------------------------------ */

function goTo(screenId) {
    // 화면 3을 벗어나는 순간(뒤로 가기·다음 단계·처음으로) 도입부 음성과 북뷰어를 멈춘다.
    // 화면 전환 지점을 한 곳으로 모아 두면 버튼을 추가해도 정지가 새지 않는다 —
    // 백그라운드에서 성우 목소리가 계속 나오면 워크숍 진행이 방해된다.
    // 북뷰어는 소리뿐 아니라 자동 넘김 타이머까지 정리해야 한다. 타이머가 살아 있으면
    // 다른 화면에 있는 동안 페이지가 혼자 넘어가고, 돌아왔을 때 엉뚱한 쪽이 펼쳐진다.
    if (screenId !== 'screen3') {
        stopIntroAudio();
        stopBookViewer();
    }
    document.querySelectorAll('.screen').forEach((node) => node.classList.remove('active'));
    document.getElementById(screenId).classList.add('active');
}

/* ------------------------------------------------------------------ */
/* 화면 2: 서가 목록                                                    */
/* ------------------------------------------------------------------ */

function clearChildren(node) {
    while (node.firstChild) {
        node.removeChild(node.firstChild);
    }
}

function renderBookGridMessage(message) {
    clearChildren(el.bookGrid);
    const msg = document.createElement('div');
    msg.className = 'book-grid-empty';
    msg.textContent = message;
    el.bookGrid.appendChild(msg);
}

// 표지 없는(또는 로드 실패한) 카드 — 이모지 + 키워드 + 큰 제목 레이아웃.
function renderCardFallback(card, story) {
    clearChildren(card);
    card.className = 'book-card no-cover';

    const emoji = document.createElement('div');
    emoji.className = 'book-emoji';
    emoji.textContent = story.emoji || '📖';

    const textWrap = document.createElement('div');
    textWrap.className = 'book-text-wrap';

    const keyword = document.createElement('span');
    keyword.className = 'book-keyword';
    keyword.textContent = story.keyword || '';

    const title = document.createElement('span');
    title.className = 'book-title';
    title.textContent = story.title || '';

    textWrap.appendChild(keyword);
    textWrap.appendChild(title);
    card.appendChild(emoji);
    card.appendChild(textWrap);
}

function renderBookGrid(stories) {
    clearChildren(el.bookGrid);
    if (!stories.length) {
        renderBookGridMessage('아직 등록된 이야기가 없어요.');
        return;
    }
    stories.forEach((story) => {
        const card = document.createElement('div');

        // 표지 이미지가 있으면 그림이 카드를 가득 채우고 아래에 [키워드] 제목만 작게 얹는다.
        // 없거나 404 면 이모지+큰제목 레이아웃으로 폴백한다(빈 액자를 남기지 않는다).
        if (story.cover_image) {
            card.className = 'book-card has-cover';

            const cover = document.createElement('img');
            cover.className = 'book-cover';
            cover.alt = '';
            cover.loading = 'lazy';
            cover.onerror = () => { renderCardFallback(card, story); };
            cover.src = story.cover_image;

            const caption = document.createElement('div');
            caption.className = 'book-caption';

            const capKeyword = document.createElement('span');
            capKeyword.className = 'cap-keyword';
            capKeyword.textContent = story.keyword ? '[' + story.keyword + ']' : '';

            const capTitle = document.createElement('span');
            capTitle.className = 'cap-title';
            capTitle.textContent = story.title || '';

            caption.appendChild(capKeyword);
            caption.appendChild(capTitle);
            card.appendChild(cover);
            card.appendChild(caption);
        } else {
            renderCardFallback(card, story);
        }

        // 원작 전문이 준비되지 않은 이야기는 잠근다. 열어도 요약 두 문장뿐이라
        // 미완성으로 읽히므로, 완성된 이야기로만 흐름을 유도한다.
        if (story.locked) {
            card.classList.add('locked');

            const lock = document.createElement('div');
            lock.className = 'book-lock';

            const icon = document.createElement('div');
            icon.className = 'book-lock-icon';
            icon.textContent = '🔒';

            lock.appendChild(icon);
            card.appendChild(lock);

            card.addEventListener('click', () => shakeLockedCard(card, story));
        } else {
            card.addEventListener('click', () => selectStory(story.id));
        }
        el.bookGrid.appendChild(card);
    });
}

// 잠긴 카드를 누르면 카드가 흔들리고 안내가 잠깐 뜬다. 아무 반응이 없으면
// 고장으로 보이므로, 눌렀다는 사실은 돌려주되 진행은 막는다.
let lockToastTimer = null;

function shakeLockedCard(card, story) {
    card.classList.remove('shake');
    void card.offsetWidth;  // 애니메이션 재시작을 위한 리플로 강제
    card.classList.add('shake');
    card.addEventListener('animationend', () => card.classList.remove('shake'), { once: true });

    const title = story.title || '이 이야기';
    el.lockToast.textContent = '「' + title + '」은 아직 준비 중이에요. 지금은 콩쥐팥쥐전을 만나보세요!';
    el.lockToast.classList.add('show');
    clearTimeout(lockToastTimer);
    lockToastTimer = setTimeout(() => el.lockToast.classList.remove('show'), 2600);
}

async function loadStories() {
    renderBookGridMessage('이야기를 불러오는 중...');
    el.storyCount.textContent = '전래동화 0권';
    try {
        const stories = await api.getStories();
        state.stories = Array.isArray(stories) ? stories : [];
        renderBookGrid(state.stories);
        el.storyCount.textContent = '전래동화 ' + state.stories.length + '권';
    } catch (err) {
        console.error('failed to load stories', err);
        renderBookGridMessage('이야기를 불러오지 못했어요. 다시 시도해 주세요.');
    }
}

/* ------------------------------------------------------------------ */
/* 화면 3: 이야기 앞부분                                                */
/* ------------------------------------------------------------------ */

// 딱지본 스캔은 아직 확보되지 않은 이야기가 있다. 경로가 없거나 파일이 404 면
// 빈 액자가 남지 않도록 영역째 숨긴다(요약 텍스트만으로도 화면이 성립한다).
function showIntroImage(path) {
    if (!path) {
        el.introImageWrap.style.display = 'none';
        return;
    }
    el.introImage.onerror = () => { el.introImageWrap.style.display = 'none'; };
    el.introImage.onload = () => { el.introImageWrap.style.display = 'block'; };
    el.introImage.src = path;
}

/* --- 도입부 음성 --------------------------------------------------- */
/* mp3 는 사전 생성해 커밋한 정적 자산이다(backend/scripts/generate_intro_audio.py).
   런타임 TTS 호출은 없으므로 재생 실패 지점은 파일 404 하나뿐 — 그때는 버튼을 숨긴다. */

function setIntroAudioIdle() {
    el.introAudioBtn.classList.remove('playing');
    el.introAudioIcon.textContent = '▶';
    el.introAudioLabel.textContent = '이야기 들려주기';
}

function setIntroAudioPlaying() {
    el.introAudioBtn.classList.add('playing');
    el.introAudioIcon.textContent = '❚❚';
    el.introAudioLabel.textContent = '들려주는 중... (누르면 멈춰요)';
}

function stopIntroAudio() {
    if (!el.introAudio) {
        return;
    }
    el.introAudio.pause();
    el.introAudio.currentTime = 0;
    setIntroAudioIdle();
}

// 음성이 없는 이야기(경로 없음 또는 404)는 버튼째 숨긴다 — 표지·딱지본 스캔과 같은
// 폴백 규칙이다. 요약 텍스트만으로도 화면은 성립한다.
function showIntroAudio(path) {
    stopIntroAudio();
    if (!path) {
        el.introAudioBtn.style.display = 'none';
        el.introAudio.removeAttribute('src');
        return;
    }
    el.introAudio.src = path;
    el.introAudioBtn.style.display = 'flex';
}

function toggleIntroAudio() {
    if (el.introAudio.paused) {
        // autoplay 금지 — 이 클릭이 유일한 재생 시작점이다(진행자가 눌러 시작).
        const playing = el.introAudio.play();
        if (playing && typeof playing.catch === 'function') {
            playing.catch((err) => {
                console.error('intro audio play failed', err);
                setIntroAudioIdle();
            });
        }
    } else {
        el.introAudio.pause();
    }
}

function initIntroAudio() {
    el.introAudioBtn.addEventListener('click', toggleIntroAudio);
    // 상태 표시는 audio 이벤트에만 의존한다 — 버튼 클릭 시점에 미리 바꾸면
    // 재생이 실패했을 때 "듣는 중"으로 굳는다.
    el.introAudio.addEventListener('play', setIntroAudioPlaying);
    el.introAudio.addEventListener('pause', setIntroAudioIdle);
    el.introAudio.addEventListener('ended', setIntroAudioIdle);
    el.introAudio.addEventListener('error', () => {
        if (el.introAudio.getAttribute('src')) {
            console.error('intro audio load failed', el.introAudio.getAttribute('src'));
            el.introAudioBtn.style.display = 'none';
        }
    });
}

/* ------------------------------------------------------------------ */
/* 화면 3: 북뷰어 — 원작 전문을 그림책처럼 넘겨 본다                    */
/* ------------------------------------------------------------------ */
/* 아이가 원작을 끝까지 알아야 "두꺼비 대신 호랑이가 왔으면" 같은 변형을 말할 수 있다.
   intro_pages 가 없는 이야기는 기존 요약 카드로 폴백한다(표지·음성과 같은 폴백 철학). */

// ended 후 다음 쪽까지의 여유. 그림을 한 박자 더 보고 넘어가게 하는 간격이라
// 음성이 없는 쪽(글자 수 타이머)에도 똑같이 붙인다.
const PAGE_GAP_MS = 1500;
// 음성이 없을 때의 낭독 시간 추정 — 성우 톤(rate -20%) 기준 대략 초당 6자.
const CHARS_PER_SEC = 6;
const MIN_READ_MS = 4000;

const book = {
    pages: [],
    index: 0,
    playing: false,   // 자동 진행 중인가
    timer: null,      // 다음 쪽 예약(setTimeout) — 화면을 벗어날 때 반드시 정리한다
    muted: false,
    audioCtx: null,
    // 방금 일어난 pause 가 우리 코드가 부른 것인지 표시한다. 브라우저·OS 가 대신 멈춘
    // 경우(태블릿 화면 잠금, 탭 백그라운드)만 일시정지로 승격시키기 위해 필요하다 —
    // 자동 넘김 중 쪽을 바꿀 때도 pause() 를 부르므로 둘을 구분하지 않으면 진행이 끊긴다.
    selfPause: false
};

/* --- 넘김 소리: Web Audio 합성 ------------------------------------- */
/* 외부 음원 파일은 공모전 제출물의 라이선스 문제가 되므로 쓰지 않는다.
   짧은 노이즈 버스트에 빠른 어택 + 완만한 감쇠 엔벨로프를 걸고 밴드패스로 다듬어
   종이 스치는 소리를 흉내 낸다. */

function ensureAudioCtx() {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) {
        return null;
    }
    if (!book.audioCtx) {
        book.audioCtx = new Ctor();
    }
    // 사용자 제스처 이전에 만들어진 컨텍스트는 suspended 로 시작한다.
    if (book.audioCtx.state === 'suspended') {
        book.audioCtx.resume().catch(() => { /* 재생만 못 할 뿐 진행은 막지 않는다 */ });
    }
    return book.audioCtx;
}

function playPageTurnSound() {
    if (book.muted) {
        return;
    }
    const ctx = ensureAudioCtx();
    if (!ctx) {
        return;
    }
    const duration = 0.16;
    const frames = Math.floor(ctx.sampleRate * duration);
    const buffer = ctx.createBuffer(1, frames, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < frames; i++) {
        const t = i / frames;
        // 어택 2ms 남짓(t * 40) + 지수적 감쇠 — 딱 한 번 '사악' 스치는 모양.
        const envelope = Math.min(1, t * 40) * Math.pow(1 - t, 2.5);
        data[i] = (Math.random() * 2 - 1) * envelope;
    }

    const source = ctx.createBufferSource();
    source.buffer = buffer;

    // 저역(웅웅거림)과 초고역(치찰음)을 깎아 종이 질감 대역만 남긴다.
    const filter = ctx.createBiquadFilter();
    filter.type = 'bandpass';
    filter.frequency.value = 2600;
    filter.Q.value = 0.6;

    // 성우 음성을 덮지 않도록 아주 낮게. 넘김 소리는 신호일 뿐 주인공이 아니다.
    const gain = ctx.createGain();
    gain.gain.value = 0.05;

    source.connect(filter);
    filter.connect(gain);
    gain.connect(ctx.destination);
    source.start();
}

function toggleBookMute() {
    book.muted = !book.muted;
    el.bookMuteBtn.classList.toggle('muted', book.muted);
    el.bookMuteBtn.textContent = book.muted ? '🔕' : '🔔';
    el.bookMuteBtn.setAttribute('aria-label', book.muted ? '넘기는 소리 켜기' : '넘기는 소리 끄기');
}

/* --- 자동 진행 ------------------------------------------------------ */

function readDurationMs(text) {
    const chars = (text || '').length;
    return Math.max(MIN_READ_MS, Math.round((chars / CHARS_PER_SEC) * 1000));
}

// 타이머 해제는 이 함수 하나로만 한다 — 해제 지점이 흩어지면 반드시 하나가 샌다.
function clearBookTimer() {
    if (book.timer !== null) {
        clearTimeout(book.timer);
        book.timer = null;
    }
}

function isLastPage() {
    return book.index >= book.pages.length - 1;
}

function setBookPlayButton() {
    el.bookPlayIcon.textContent = book.playing ? '❚❚' : '▶';
    if (book.playing) {
        el.bookPlayLabel.textContent = '잠깐 멈추기';
        return;
    }
    // 첫 쪽 도중에 멈춘 경우까지 "시작"이라고 쓰면 처음부터 다시 읽는 것처럼 보인다.
    // 실제로는 멈춘 자리에서 이어 재생하므로 재생 진척이 있으면 "이어서"로 쓴다.
    const started = book.index > 0 || (el.bookAudio.getAttribute('src') && el.bookAudio.currentTime > 0);
    el.bookPlayLabel.textContent = started ? '이어서 듣기' : '이야기 시작';
}

function setBookSkipButton() {
    // 마지막 쪽에서는 "건너뛰기"가 아니라 다음 단계로 가는 주 버튼이 된다.
    const finished = isLastPage();
    el.bookSkipBtn.classList.toggle('is-finish', finished);
    el.bookSkipBtn.textContent = finished ? '이제 내가 바꿔볼래!' : '그냥 넘어갈래요';
}

function updateBookControls() {
    el.bookIndicator.textContent = (book.index + 1) + ' / ' + book.pages.length;
    el.bookPrevBtn.disabled = book.index === 0;
    el.bookNextBtn.disabled = isLastPage();
    setBookPlayButton();
    setBookSkipButton();
}

// 우리 코드가 부르는 pause. 아래 'pause' 핸들러가 이 정지를 외부 중단으로 오인하지
// 않도록 표시해 둔다. 이미 멈춘 상태면 이벤트가 나지 않으므로 표시하지 않는다.
function pauseAudioFromCode() {
    if (!el.bookAudio.paused) {
        book.selfPause = true;
    }
    el.bookAudio.pause();
}

// 페이지 음성을 원점으로 돌린다. 쪽을 옮길 때마다 불러 이전 쪽 음성이 남지 않게 한다.
function resetPageAudio() {
    pauseAudioFromCode();
    el.bookAudio.removeAttribute('src');
    el.bookAudio.load();
}

function renderBookPage(direction) {
    const page = book.pages[book.index];
    if (!page) {
        return;
    }
    el.bookText.textContent = page.text || '';

    // 삽화가 아직 없는 쪽(경로 빈 문자열)이나 404 는 플레이스홀더로 채운다.
    // 파일이 들어오면 시딩이 경로를 채우고 그대로 표시된다 — 프론트 수정은 필요 없다.
    el.bookIllust.classList.remove('has-image');
    if (page.image) {
        el.bookIllustImg.onload = () => { el.bookIllust.classList.add('has-image'); };
        el.bookIllustImg.onerror = () => { el.bookIllust.classList.remove('has-image'); };
        el.bookIllustImg.src = page.image;
    } else {
        el.bookIllustImg.removeAttribute('src');
    }

    // 애니메이션 클래스를 뗐다가 리플로우를 강제한 뒤 다시 붙여야 같은 방향으로
    // 연속해서 넘길 때도 매번 재생된다.
    el.bookSheet.classList.remove('turn-next', 'turn-prev');
    void el.bookSheet.offsetWidth;
    el.bookSheet.classList.add(direction === 'prev' ? 'turn-prev' : 'turn-next');

    updateBookControls();
}

function gotoPage(index, direction) {
    if (index < 0 || index >= book.pages.length) {
        return;
    }
    clearBookTimer();
    resetPageAudio();
    book.index = index;
    renderBookPage(direction);
    playPageTurnSound();
}

function scheduleNextPage(delayMs) {
    clearBookTimer();
    book.timer = setTimeout(() => {
        book.timer = null;
        if (!book.playing) {
            return;
        }
        if (isLastPage()) {
            // 마지막 쪽을 다 읽으면 자동 진행을 끝낸다(첫 쪽으로 되돌아가지 않는다).
            book.playing = false;
            updateBookControls();
            return;
        }
        gotoPage(book.index + 1, 'next');
        playCurrentPage();
    }, delayMs);
}

function playCurrentPage() {
    clearBookTimer();
    const page = book.pages[book.index];
    if (!page) {
        return;
    }
    // 음성이 없는 쪽은 글자 수로 낭독 시간을 추정해 같은 리듬을 유지한다.
    if (!page.audio) {
        scheduleNextPage(readDurationMs(page.text) + PAGE_GAP_MS);
        return;
    }
    el.bookAudio.src = page.audio;
    playPageAudio(() => {
        // 재생을 못 하면(자동재생 차단·디코드 실패) 이야기가 멈추지 않게 타이머로 이어간다.
        scheduleNextPage(readDurationMs(page.text) + PAGE_GAP_MS);
    });
}

// play() 는 promise 다. 재생이 시작되기 전에 pause() 가 끼어들면 AbortError 로 거부되는데,
// 이것은 "빠르게 다음 쪽을 눌렀다" 같은 정상적인 조작의 결과라 에러로 취급하지 않는다.
// 진짜 실패(차단·디코드 오류)일 때만 폴백을 태운다.
function playPageAudio(onFailure) {
    const playing = el.bookAudio.play();
    if (!playing || typeof playing.catch !== 'function') {
        return;
    }
    playing.catch((err) => {
        if (err && err.name === 'AbortError') {
            return;
        }
        if (!book.playing) {
            return;
        }
        console.error('book page audio play failed', err);
        onFailure();
    });
}

// 일시정지 — 음성과 자동 넘김을 함께 멈춘다. 둘 중 하나만 멈추면 화면과 소리가 어긋난다.
function pauseBook() {
    book.playing = false;
    clearBookTimer();
    pauseAudioFromCode();
    updateBookControls();
}

function startBook() {
    book.playing = true;
    updateBookControls();
    // 이 클릭이 소리의 유일한 시작점이다(autoplay 금지 — 진입 즉시 소리가 나면 안 된다).
    ensureAudioCtx();
    // 음성 도중에 멈춘 것이면 그 자리에서 이어 재생한다.
    const page = book.pages[book.index];
    if (el.bookAudio.getAttribute('src') && !el.bookAudio.ended && el.bookAudio.currentTime > 0) {
        playPageAudio(() => {
            const remaining = Math.max(0, (el.bookAudio.duration || 0) - el.bookAudio.currentTime);
            scheduleNextPage(Math.round(remaining * 1000) + PAGE_GAP_MS);
        });
        return;
    }
    if (!page) {
        return;
    }
    playCurrentPage();
}

function toggleBookPlay() {
    if (book.playing) {
        pauseBook();
    } else {
        startBook();
    }
}

// 빠른 넘김 — 아이가 그림을 더 보려는 신호로 읽고 자동 진행을 일시정지로 돌린다.
function stepBookPage(delta) {
    const next = book.index + delta;
    if (next < 0 || next >= book.pages.length) {
        return;
    }
    pauseBook();
    gotoPage(next, delta < 0 ? 'prev' : 'next');
}

// 화면을 벗어날 때의 완전 정지 — 음성·타이머·애니메이션 클래스까지 원점으로.
function stopBookViewer() {
    if (!el.bookAudio) {
        return;
    }
    book.playing = false;
    clearBookTimer();
    resetPageAudio();
    book.selfPause = false;
    if (el.bookSheet) {
        el.bookSheet.classList.remove('turn-next', 'turn-prev');
    }
}

function showBookViewer(pages) {
    stopBookViewer();
    book.pages = Array.isArray(pages) ? pages : [];
    book.index = 0;

    const hasPages = book.pages.length > 0;
    el.bookViewer.style.display = hasPages ? 'flex' : 'none';
    el.bookViewerBottom.style.display = hasPages ? 'block' : 'none';
    // 폴백(요약 카드)과 북뷰어는 동시에 뜨지 않는다 — 같은 이야기를 두 번 보여주게 된다.
    el.introFallback.style.display = hasPages ? 'none' : 'block';
    el.introFallbackBottom.style.display = hasPages ? 'none' : 'block';
    if (!hasPages) {
        return;
    }
    renderBookPage('next');
}

function initBookViewer() {
    el.bookPlayBtn.addEventListener('click', toggleBookPlay);
    el.bookPrevBtn.addEventListener('click', () => stepBookPage(-1));
    el.bookNextBtn.addEventListener('click', () => stepBookPage(1));
    el.bookMuteBtn.addEventListener('click', toggleBookMute);
    el.bookSkipBtn.addEventListener('click', () => {
        resetSpeechState();
        goTo('screen4');
    });

    // 자동 진행의 기준 신호. 음성이 끝나야 다음 쪽으로 넘어간다.
    el.bookAudio.addEventListener('ended', () => {
        if (book.playing) {
            scheduleNextPage(PAGE_GAP_MS);
        }
    });
    // 우리가 부르지 않은 정지(태블릿 화면 잠금, 탭 백그라운드 전환)를 일시정지로 반영한다.
    // 재생 중 상태로 남겨 두면 예약된 타이머도 없어 이야기가 조용히 굳고, 버튼에는
    // "잠깐 멈추기"가 떠 있어 진행자가 왜 멈췄는지 알 수 없다.
    el.bookAudio.addEventListener('pause', () => {
        if (book.selfPause) {
            book.selfPause = false;
            return;
        }
        if (book.playing && !el.bookAudio.ended) {
            pauseBook();
        }
    });
    // 음성 파일이 깨졌거나 404 여도 이야기가 멈추면 안 된다 — 글자 수 타이머로 이어간다.
    el.bookAudio.addEventListener('error', () => {
        if (!el.bookAudio.getAttribute('src') || !book.playing) {
            return;
        }
        const page = book.pages[book.index];
        console.error('book page audio load failed', el.bookAudio.getAttribute('src'));
        scheduleNextPage(readDurationMs(page && page.text) + PAGE_GAP_MS);
    });
}

async function selectStory(id) {
    try {
        const detail = await api.getStory(id);
        state.currentStory = detail;
        el.storyTitle.textContent = detail.title || '';
        el.introSummary.textContent = detail.intro_summary || '';
        showIntroImage(detail.intro_image);
        // 이야기마다 무엇을 상상할지가 다르다(콩쥐팥쥐: 물독을 어떻게 채울까).
        // 시드에 질문이 없으면 기본 문구를 그대로 둔다.
        if (detail.question) {
            el.askQuestion.textContent = detail.question;
        } else {
            el.askQuestion.textContent = '이 뒤에는 어떤 일이 일어났을까요?';
        }
        showIntroAudio(detail.intro_audio);
        showBookViewer(detail.intro_pages);
    } catch (err) {
        console.error('failed to load story detail', err);
        state.currentStory = { id: id, title: '' };
        el.storyTitle.textContent = '-';
        el.introSummary.textContent = '이야기를 불러오지 못했어요. 다시 시도해 주세요.';
        showIntroImage(null);
        showIntroAudio(null);
        showBookViewer([]);
    }
    goTo('screen3');
}

/* ------------------------------------------------------------------ */
/* 화면 4: 구술 입력 + Web Speech API                                  */
/* ------------------------------------------------------------------ */

function updateAiButtonState() {
    const text = el.sttBox.textContent.trim();
    el.aiBtn.disabled = text.length < 1;
}

function resetSpeechState() {
    if (recognition && state.recognizing) {
        try {
            recognition.stop();
        } catch (err) {
            /* ignore */
        }
    }
    state.finalTranscript = '';
    el.sttBox.textContent = '';
    hideGenerateError();
    updateAiButtonState();
}

function setMicIdleStyle() {
    el.micBtn.style.animation = 'pulse 2s infinite';
    el.micBtn.style.backgroundColor = 'var(--primary-celadon)';
}

function setMicActiveStyle() {
    el.micBtn.style.animation = 'pulse 1s infinite';
    el.micBtn.style.backgroundColor = 'var(--accent-red)';
}

function handleRecognitionResult(event) {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
            state.finalTranscript += transcript;
        } else {
            interim += transcript;
        }
    }
    el.sttBox.textContent = (state.finalTranscript + interim).trim();
    updateAiButtonState();
}

function handleRecognitionEnd() {
    state.recognizing = false;
    setMicIdleStyle();
}

function handleRecognitionError(event) {
    console.error('speech recognition error', event.error);
    state.recognizing = false;
    setMicIdleStyle();
}

function toggleRecord() {
    if (!recognition) {
        return;
    }
    if (!state.recognizing) {
        recognition.lang = state.lang === 'en' ? 'en-US' : 'ko-KR';
        try {
            recognition.start();
            state.recognizing = true;
            setMicActiveStyle();
        } catch (err) {
            console.error('failed to start recognition', err);
        }
    } else {
        recognition.stop();
    }
}

function initSpeechRecognition() {
    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
        el.micBtn.disabled = true;
        el.micUnsupportedNote.classList.add('visible');
        return;
    }
    recognition = new SpeechRecognitionCtor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = handleRecognitionResult;
    recognition.onerror = handleRecognitionError;
    recognition.onend = handleRecognitionEnd;
}

function showGenerateError() {
    el.generateError.classList.add('visible');
}

function hideGenerateError() {
    el.generateError.classList.remove('visible');
}

/* ------------------------------------------------------------------ */
/* AI 생성                                                             */
/* ------------------------------------------------------------------ */

async function handleGenerate() {
    if (!state.currentStory || state.currentStory.id === undefined) {
        return;
    }
    const childSpeech = el.sttBox.textContent.trim();
    if (childSpeech.length < 1) {
        return;
    }
    hideGenerateError();
    goTo('loadingScreen');
    try {
        const data = await api.generateStory(state.currentStory.id, {
            lang: state.lang,
            child_speech: childSpeech
        });
        state.sessionId = data.session_id;
        state.pages = Array.isArray(data.pages) ? data.pages : [];
        state.keywords = Array.isArray(data.keywords) ? data.keywords : [];
        renderPdfPages(state.pages);
        goTo('screen5');
    } catch (err) {
        console.error('generate failed', err);
        goTo('screen4');
        showGenerateError();
    }
}

/* ------------------------------------------------------------------ */
/* 화면 5: 완성본 / PDF                                                 */
/* ------------------------------------------------------------------ */

function renderPdfPages(pages) {
    clearChildren(el.pdfScrollBox);
    pages.forEach((page) => {
        const pageEl = document.createElement('div');
        pageEl.className = 'pdf-page';

        const drawArea = document.createElement('div');
        drawArea.className = 'pdf-draw-area';
        drawArea.textContent = '그림 그리는 곳';

        const textArea = document.createElement('div');
        textArea.className = 'pdf-text-area';
        textArea.appendChild(document.createTextNode(page.ko || ''));

        const enLine = document.createElement('div');
        enLine.className = 'pdf-text-en';
        enLine.textContent = page.en || '';
        textArea.appendChild(enLine);

        pageEl.appendChild(drawArea);
        pageEl.appendChild(textArea);
        el.pdfScrollBox.appendChild(pageEl);
    });
}

function showPdfError() {
    el.pdfError.classList.add('visible');
}

function hidePdfError() {
    el.pdfError.classList.remove('visible');
}

function pdfFileName() {
    // 파일명에는 아이 이름을 넣지 않는다 — 다운로드 폴더에 이름이 남기 때문.
    const title = (state.currentStory && state.currentStory.title) || '우리동화';
    return title.replace(/[\\/:*?"<>|]/g, '') + '_동화책.pdf';
}

async function handleDownloadPdf() {
    if (!state.sessionId) {
        return;
    }
    const authorName = el.authorNameInput.value.trim();
    hidePdfError();
    el.downloadPdfBtn.disabled = true;
    try {
        const blob = await api.fetchPdfBlob(state.sessionId, authorName);
        const objectUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = objectUrl;
        link.download = pdfFileName();
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(objectUrl);
    } catch (err) {
        console.error('pdf download failed', err);
        showPdfError();
    } finally {
        el.downloadPdfBtn.disabled = false;
    }
}

/* ------------------------------------------------------------------ */
/* 영수증 모달                                                          */
/* ------------------------------------------------------------------ */

function formatNow() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return y + '. ' + m + '. ' + d;
}

function renderReceiptBooks(books) {
    clearChildren(el.receiptBooks);
    if (!books || !books.length) {
        const empty = document.createElement('div');
        empty.textContent = '추천 도서가 없어요.';
        el.receiptBooks.appendChild(empty);
        return;
    }
    books.forEach((book, idx) => {
        const row = document.createElement('div');
        row.className = 'receipt-book-row';

        const name = document.createElement('span');
        name.className = 'receipt-book-title';
        name.textContent = (idx + 1) + '. ' + (book.title || '');
        row.appendChild(name);

        // 청구기호가 없는 응답도 있다(정보나루 class_no 결측). 빈 회색 조각이 남지 않게 건너뛴다.
        if (book.call_number) {
            const code = document.createElement('strong');
            code.className = 'receipt-book-code';
            code.textContent = book.call_number;
            row.appendChild(code);
        }
        el.receiptBooks.appendChild(row);
    });
}

async function openReceipt() {
    if (!state.sessionId) {
        return;
    }
    const storyTitle = (state.currentStory && state.currentStory.title) || '';
    el.receiptDate.textContent = formatNow();
    el.receiptBookTitle.textContent = (storyTitle + ' (창작본)').trim();
    el.receiptAuthor.textContent = el.authorNameInput.value.trim() || '이름 없는 꼬마 작가';
    el.receiptKeywords.textContent = state.keywords.length
        ? state.keywords.map((kw) => '#' + kw).join(' ')
        : '-';
    el.receiptBooksTitle.textContent = '[ 📚 추천 도서를 찾는 중... ]';
    clearChildren(el.receiptBooks);

    el.receiptModal.style.display = 'flex';

    try {
        const data = await api.getRecommendations(state.sessionId);
        const label = data.fallback ? '사서 추천 도서' : '아이의 생각과 닮은 책';
        el.receiptBooksTitle.textContent = '[ 📚 ' + label + ' ]';
        renderReceiptBooks(data.books);
    } catch (err) {
        console.error('failed to load recommendations', err);
        el.receiptBooksTitle.textContent = '[ 📚 추천 도서 ]';
        clearChildren(el.receiptBooks);
        const errEl = document.createElement('div');
        errEl.textContent = '추천 도서를 불러오지 못했어요.';
        el.receiptBooks.appendChild(errEl);
    }
}

function closeReceipt() {
    el.receiptModal.style.display = 'none';
}

/* ------------------------------------------------------------------ */
/* 처음으로                                                             */
/* ------------------------------------------------------------------ */

function goHome() {
    state.currentStory = null;
    state.sessionId = null;
    state.pages = [];
    state.keywords = [];
    el.authorNameInput.value = '';
    hidePdfError();
    clearChildren(el.pdfScrollBox);
    resetSpeechState();
    goTo('screen1');
}

/* ------------------------------------------------------------------ */
/* 초기화                                                              */
/* ------------------------------------------------------------------ */

function selectLang(lang) {
    state.lang = lang;
    goTo('screen2');
    loadStories();
}

function init() {
    el = {
        langKoBtn: document.getElementById('langKoBtn'),
        langEnBtn: document.getElementById('langEnBtn'),
        backToScreen1: document.getElementById('backToScreen1'),
        backToScreen2: document.getElementById('backToScreen2'),
        backToScreen3: document.getElementById('backToScreen3'),
        storyCount: document.getElementById('storyCount'),
        bookGrid: document.getElementById('bookGrid'),
        storyTitle: document.getElementById('storyTitle'),
        introSummary: document.getElementById('introSummary'),
        lockToast: document.getElementById('lockToast'),
        askQuestion: document.getElementById('askQuestion'),
        introImageWrap: document.getElementById('introImageWrap'),
        introImage: document.getElementById('introImage'),
        introAudioBtn: document.getElementById('introAudioBtn'),
        introAudioIcon: document.getElementById('introAudioIcon'),
        introAudioLabel: document.getElementById('introAudioLabel'),
        introAudio: document.getElementById('introAudio'),
        introFallback: document.getElementById('introFallback'),
        introFallbackBottom: document.getElementById('introFallbackBottom'),
        bookViewer: document.getElementById('bookViewer'),
        bookViewerBottom: document.getElementById('bookViewerBottom'),
        bookSheet: document.getElementById('bookSheet'),
        bookIllust: document.getElementById('bookIllust'),
        bookIllustImg: document.getElementById('bookIllustImg'),
        bookText: document.getElementById('bookText'),
        bookIndicator: document.getElementById('bookIndicator'),
        bookMuteBtn: document.getElementById('bookMuteBtn'),
        bookPrevBtn: document.getElementById('bookPrevBtn'),
        bookNextBtn: document.getElementById('bookNextBtn'),
        bookPlayBtn: document.getElementById('bookPlayBtn'),
        bookPlayIcon: document.getElementById('bookPlayIcon'),
        bookPlayLabel: document.getElementById('bookPlayLabel'),
        bookSkipBtn: document.getElementById('bookSkipBtn'),
        bookAudio: document.getElementById('bookAudio'),
        goScreen4Btn: document.getElementById('goScreen4Btn'),
        micBtn: document.getElementById('micBtn'),
        micUnsupportedNote: document.getElementById('micUnsupportedNote'),
        sttBox: document.getElementById('sttBox'),
        generateError: document.getElementById('generateError'),
        aiBtn: document.getElementById('aiBtn'),
        pdfScrollBox: document.getElementById('pdfScrollBox'),
        authorNameInput: document.getElementById('authorNameInput'),
        downloadPdfBtn: document.getElementById('downloadPdfBtn'),
        pdfError: document.getElementById('pdfError'),
        receiptBanner: document.getElementById('receiptBanner'),
        receiptModal: document.getElementById('receiptModal'),
        closeReceiptBtn: document.getElementById('closeReceiptBtn'),
        receiptDate: document.getElementById('receiptDate'),
        receiptBookTitle: document.getElementById('receiptBookTitle'),
        receiptAuthor: document.getElementById('receiptAuthor'),
        receiptKeywords: document.getElementById('receiptKeywords'),
        receiptBooksTitle: document.getElementById('receiptBooksTitle'),
        receiptBooks: document.getElementById('receiptBooks'),
        printLocationBtn: document.getElementById('printLocationBtn'),
        goHomeBtn: document.getElementById('goHomeBtn')
    };

    el.langKoBtn.addEventListener('click', () => selectLang('ko'));
    el.langEnBtn.addEventListener('click', () => selectLang('en'));

    el.backToScreen1.addEventListener('click', () => goTo('screen1'));
    el.backToScreen2.addEventListener('click', () => goTo('screen2'));
    el.backToScreen3.addEventListener('click', () => goTo('screen3'));

    el.goScreen4Btn.addEventListener('click', () => {
        resetSpeechState();
        goTo('screen4');
    });

    el.micBtn.addEventListener('click', toggleRecord);
    el.sttBox.addEventListener('input', () => {
        state.finalTranscript = el.sttBox.textContent;
        updateAiButtonState();
    });
    el.aiBtn.addEventListener('click', handleGenerate);

    el.downloadPdfBtn.addEventListener('click', handleDownloadPdf);

    el.receiptBanner.addEventListener('click', openReceipt);
    el.closeReceiptBtn.addEventListener('click', closeReceipt);
    el.printLocationBtn.addEventListener('click', () => {
        alert('징징징~ 🖨️\n도서관 프린터에서 청구기호표(위치표)가 출력되었습니다!\n책을 찾으러 서가로 이동해 보세요.');
    });

    el.goHomeBtn.addEventListener('click', goHome);

    initIntroAudio();
    initBookViewer();
    initSpeechRecognition();
    updateAiButtonState();
}

document.addEventListener('DOMContentLoaded', init);
