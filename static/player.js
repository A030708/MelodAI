(function () {
  'use strict';

  // Stop all audio playback when leaving the recommendation page
  window.addEventListener('beforeunload', function () {
    var players = document.querySelectorAll('audio');
    players.forEach(function (p) {
      p.pause();
      p.src = '';
    });
    var persistentPlayer = document.getElementById('persistent-player') || document.getElementById('mini-player');
    if (persistentPlayer) {
      var audio = persistentPlayer.querySelector('audio');
      if (audio) {
        audio.pause();
        audio.src = '';
      }
    }
  });

  // On page load, check if we are on recommendation page
  document.addEventListener('DOMContentLoaded', function () {
    var path = window.location.pathname;
    var isRecPage = (path === '/' || path === '/index');
    if (!isRecPage) {
      var selectors = [
        '#persistent-player',
        '#mini-player',
        '.player-bar',
        '.bottom-player',
        '#bottom-player',
        '#now-playing-bar',
        '.now-playing-bar',
        '.music-player-footer'
      ];
      selectors.forEach(function (sel) {
        var el = document.querySelector(sel);
        if (el) {
          el.style.display = 'none';
          var audio = el.querySelector('audio');
          if (audio) {
            audio.pause();
            audio.src = '';
          }
        }
      });
      var allAudio = document.querySelectorAll('audio');
      allAudio.forEach(function (a) {
        a.pause();
        a.src = '';
      });
    }
  });

  var player = document.getElementById('shared-player');
  var mini = document.getElementById('mini-player');
  var mpTitle = document.getElementById('mp-title');
  var mpArtist = document.getElementById('mp-artist');
  var mpPlay = document.getElementById('mp-play');
  var mpFill = document.getElementById('mp-progress-fill');
  var mpBar = document.getElementById('mp-progress-bar');
  var mpQCount = document.getElementById('mp-q-count');
  var queuePanel = document.getElementById('queue-panel');
  var qpList = document.getElementById('qp-list');
  var qpCount = document.getElementById('qp-count');

  var currentSong = null;
  var queue = [];
  var isSeeking = false;

  // ── Exposed globally for inline onclick handlers ──

  window.playerToggle = function() {
    if (!player.src) return;
    if (player.paused) {
      player.play()['catch'](function(){});
    } else {
      player.pause();
    }
  };

  window.playerNext = function() {
    if (queue.length > 0) {
      playSong(queue.shift());
      saveQueue();
      renderQueue();
    } else {
      fetchNextRec();
    }
  };

  window.playerPrev = function() {
    // Restart current if more than 3s in, else go to previous if queue history
    if (player.currentTime > 3) {
      player.currentTime = 0;
    } else {
      // Simple: just restart
      player.currentTime = 0;
    }
  };

  window.playerSeek = function(e) {
    var rect = mpBar.getBoundingClientRect();
    var pct = (e.clientX - rect.left) / rect.width;
    if (player.duration) {
      player.currentTime = pct * player.duration;
    }
  };

  window.toggleQueuePanel = function() {
    var show = queuePanel.style.display === 'none' || queuePanel.style.display === '';
    queuePanel.style.display = show ? 'flex' : 'none';
    if (show) renderQueue();
  };

  window.clearQueue = function() {
    queue = [];
    saveQueue();
    renderQueue();
    updateQCount();
  };

  // ── Main play function ──

  window.playSong = function(song) {
    if (!song) return;
    currentSong = song;

    var src = '/stream/' + song.id + '?q=medium';
    var oldSrc = player.src;

    player.src = src;
    player.load();
    player.play()['catch'](function(e) {
      console.warn('[Player] Play blocked:', e);
    });

    // Update mini player UI
    mini.style.display = 'block';
    mpTitle.textContent = song.title || 'Unknown';
    mpArtist.textContent = song.artist || '';
    mpPlay.textContent = '⏸';

    // Send play event
    var csrf = document.querySelector('meta[name="csrf-token"]');
    if (csrf) {
      fetch('/event', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRF-Token': csrf.content
        },
        body: 'csrf_token=' + encodeURIComponent(csrf.content) +
              '&song_id=' + encodeURIComponent(song.song_id || 'uploaded_' + song.id) +
              '&event_type=play'
      })['catch'](function(){});
    }

    // Scroll to card if on home page
    var card = document.querySelector('.card[data-sid="' + (song.song_id || 'uploaded_' + song.id) + '"]');
    if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  // ── Player events ──

  player.addEventListener('play', function() {
    mpPlay.textContent = '⏸';
  });

  player.addEventListener('pause', function() {
    mpPlay.textContent = '▶';
  });

  player.addEventListener('timeupdate', function() {
    if (!isSeeking && player.duration) {
      var pct = (player.currentTime / player.duration) * 100;
      mpFill.style.width = pct + '%';
    }
  });

  player.addEventListener('ended', function() {
    mpPlay.textContent = '▶';
    if (queue.length > 0) {
      window.playerNext();
    } else if (currentSong) {
      // Auto-skip: send skip event
      var csrf = document.querySelector('meta[name="csrf-token"]');
      if (csrf) {
        fetch('/event', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRF-Token': csrf.content },
          body: 'csrf_token=' + encodeURIComponent(csrf.content) +
                '&song_id=' + encodeURIComponent(currentSong.song_id || 'uploaded_' + currentSong.id) +
                '&event_type=skip'
        })['catch'](function(){});
      }
      fetchNextRec();
    }
  });

  player.addEventListener('error', function() {
    console.warn('[Player] Stream error, stopping playback');
    mini.style.display = 'none';
    mpPlay.textContent = '▶';
    currentSong = null;
    player.src = '';
  });

  // ── Audio Visualizer ──

  var vizCanvas = document.getElementById('visualizer-canvas');
  var vizCtx = null;
  var analyser = null;
  var audioCtx = null;
  var source = null;
  var animFrame = null;
  var vizActive = false;

  function initVisualizer() {
    if (vizActive) return;
    if (!vizCanvas) return;
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 128;
      source = audioCtx.createMediaElementSource(player);
      source.connect(analyser);
      analyser.connect(audioCtx.destination);
      vizCtx = vizCanvas.getContext('2d');
      vizActive = true;
    } catch (e) {
      console.warn('[Visualizer] Failed to init:', e);
    }
  }

  function renderVisualizer() {
    if (!vizActive || !analyser || !vizCtx || !vizCanvas) return;
    var bufferLength = analyser.frequencyBinCount;
    var dataArray = new Uint8Array(bufferLength);
    analyser.getByteFrequencyData(dataArray);

    vizCtx.clearRect(0, 0, vizCanvas.width, vizCanvas.height);
    var w = vizCanvas.width;
    var h = vizCanvas.height;
    var barWidth = (w / bufferLength) * 2.5;
    var x = 0;

    for (var i = 0; i < bufferLength; i++) {
      var barHeight = (dataArray[i] / 255) * h;
      var hue = 140 + (i / bufferLength) * 40;
      var brightness = 50 + (dataArray[i] / 255) * 50;
      vizCtx.fillStyle = 'hsla(' + hue + ', 80%, ' + brightness + '%, 0.7)';
      vizCtx.fillRect(x, h - barHeight, barWidth - 1, barHeight);
      x += barWidth;
    }
    animFrame = requestAnimationFrame(renderVisualizer);
  }

  function resizeVisualizer() {
    if (!vizCanvas) return;
    var rect = vizCanvas.parentElement.getBoundingClientRect();
    vizCanvas.width = rect.width;
    vizCanvas.height = 60;
  }

  window.addEventListener('resize', resizeVisualizer);

  function startVisualizer() {
    if (!vizActive) {
      try { initVisualizer(); } catch (e) { return; }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    resizeVisualizer();
    if (animFrame) cancelAnimationFrame(animFrame);
    renderVisualizer();
  }

  function stopVisualizer() {
    if (animFrame) {
      cancelAnimationFrame(animFrame);
      animFrame = null;
    }
    if (vizCtx && vizCanvas) {
      vizCtx.clearRect(0, 0, vizCanvas.width, vizCanvas.height);
    }
  }

  // Hook into player events
  player.addEventListener('play', function() {
    startVisualizer();
  });

  player.addEventListener('pause', function() {
    stopVisualizer();
  });

  player.addEventListener('ended', function() {
    stopVisualizer();
  });

  player.addEventListener('error', function() {
    stopVisualizer();
  });

  // ── Fetch next recommendation ──

  function fetchNextRec() {
    fetch('/api/recommendations?limit=1')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.songs && data.songs.length > 0) {
          var next = data.songs[0];
          next.song_id = next.song_id || 'uploaded_' + next.id;
          window.playSong(next);
        }
      })['catch'](function(){});
  }

  // ── Queue management (localStorage) ──

  function saveQueue() {
    try { localStorage.setItem('melodai_queue', JSON.stringify(queue)); } catch(e) {}
  }

  function loadQueue() {
    try {
      var q = localStorage.getItem('melodai_queue');
      if (q) queue = JSON.parse(q);
    } catch(e) { queue = []; }
    updateQCount();
  }

  function updateQCount() {
    mpQCount.textContent = queue.length;
  }

  function renderQueue() {
    qpList.innerHTML = '';
    qpCount.textContent = queue.length + ' song' + (queue.length !== 1 ? 's' : '');

    if (queue.length === 0) {
      qpList.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-subdued);font-size:12px;">Queue is empty</div>';
      return;
    }

    queue.forEach(function(s, i) {
      var div = document.createElement('div');
      div.className = 'qp-item';
      div.innerHTML =
        '<div class="qp-item-info"><div class="qp-item-title">' + (s.title || 'Unknown') + '</div><div class="qp-item-artist">' + (s.artist || '') + '</div></div>' +
        '<button class="qp-item-remove" onclick="removeFromQueue(' + i + ')">✕</button>';
      qpList.appendChild(div);
    });
  }

  window.removeFromQueue = function(idx) {
    queue.splice(idx, 1);
    saveQueue();
    renderQueue();
    updateQCount();
  };

  // ── Expose addToQueue for inline use ──

  window.addToQueue = function(song) {
    queue.push(song);
    saveQueue();
    renderQueue();
    updateQCount();
    showToast('Added to queue — ' + queue.length + ' songs');
  };

  // ── Toast ──

  function showToast(message, duration) {
    duration = duration || 2500;
    var toast = document.getElementById('melodai-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'melodai-toast';
      toast.style.cssText = [
        'position: fixed', 'bottom: 76px', 'left: 50%',
        'transform: translateX(-50%)',
        'background: rgba(255,255,255,0.12)',
        'backdrop-filter: blur(14px)',
        'color: #ffffff', 'padding: 10px 26px',
        'border-radius: 24px', 'font-size: 13px',
        'font-weight: 500', 'z-index: 9999',
        'border: 1px solid rgba(255,255,255,0.18)',
        'box-shadow: 0 4px 24px rgba(0,0,0,0.3)',
        'transition: opacity 0.35s ease',
        'pointer-events: none'
      ].join(';');
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.style.opacity = '1';
    setTimeout(function() { toast.style.opacity = '0'; }, duration);
  }

  window.showToast = showToast;

  // ── Init ──

  loadQueue();

  // If there was a previously playing song in sessionStorage, resume UI
  try {
    var prev = sessionStorage.getItem('melodai_now_playing');
    if (prev) {
      var p = JSON.parse(prev);
      mini.style.display = 'block';
      mpTitle.textContent = p.title || '';
      mpArtist.textContent = p.artist || '';
    }
  } catch(e) {}

  // Save now-playing to sessionStorage on play
  player.addEventListener('playing', function() {
    if (currentSong) {
      try { sessionStorage.setItem('melodai_now_playing', JSON.stringify(currentSong)); } catch(e) {}
    }
  });

  // ── Wire up existing play buttons (index.html cards) ──
  document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.event-btn[data-event-type="play"]').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        var card = btn.closest('.card');
        if (!card) return;
        var titleEl = card.querySelector('.song-title');
        var artistEl = card.querySelector('.song-artist');
        var song = {
          id: btn.dataset.id || btn.dataset.songId.replace('uploaded_', ''),
          song_id: btn.dataset.songId,
          title: titleEl ? titleEl.textContent : 'Unknown',
          artist: artistEl ? artistEl.textContent : '',
        };
        // Add remaining queue from other cards
        buildQueueFromCards(card);
        window.playSong(song);
      });
    });

    document.querySelectorAll('.event-btn[data-event-type="addq"]').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        window.addToQueue({
          id: btn.dataset.id || btn.dataset.songId.replace('uploaded_', ''),
          song_id: btn.dataset.songId,
          title: btn.dataset.title || 'Unknown',
          artist: btn.dataset.artist || '',
        });
      });
    });
  });

  function buildQueueFromCards(currentCard) {
    var cards = Array.from(document.querySelectorAll('.card'));
    var idx = cards.indexOf(currentCard);
    if (idx < 0) return;
    var remaining = [];
    for (var i = idx + 1; i < cards.length; i++) {
      var c = cards[i];
      var titleEl = c.querySelector('.song-title');
      var artistEl = c.querySelector('.song-artist');
      var playBtn = c.querySelector('.event-btn[data-event-type="play"]');
      if (playBtn) {
        remaining.push({
          id: playBtn.dataset.id || playBtn.dataset.songId.replace('uploaded_', ''),
          song_id: playBtn.dataset.songId,
          title: titleEl ? titleEl.textContent : 'Unknown',
          artist: artistEl ? artistEl.textContent : '',
        });
      }
    }
    // Prepend remaining to existing queue
    queue = remaining.concat(queue);
    saveQueue();
    renderQueue();
    updateQCount();
  }

  // ── Notifications ──

  var notifPanel = document.getElementById('notif-panel');
  var notifList = document.getElementById('notif-list');
  var bellCount = document.getElementById('bell-count');

  window.toggleNotifications = function() {
    if (!notifPanel) return;
    var show = notifPanel.style.display === 'none' || notifPanel.style.display === '';
    notifPanel.style.display = show ? 'flex' : 'none';
    if (show) { fetchNotifs(); markNotifsRead(); }
  };

  window.markNotifsRead = function() {
    fetch('/api/notifications/read', { method: 'POST' })['catch'](function(){});
    if (bellCount) { bellCount.style.display = 'none'; bellCount.textContent = '0'; }
  };

  function fetchNotifs() {
    fetch('/api/notifications')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (bellCount) {
          if (data.unread > 0) {
            bellCount.style.display = 'flex';
            bellCount.textContent = data.unread;
          } else {
            bellCount.style.display = 'none';
          }
        }
        if (notifList) {
          notifList.innerHTML = '';
          if (data.notifications.length === 0) {
            notifList.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-subdued);font-size:12px;">No notifications</div>';
            return;
          }
          data.notifications.forEach(function(n) {
            var div = document.createElement('div');
            div.style.cssText = 'padding:10px 12px;border-radius:var(--radius-md);font-size:12px;margin-bottom:4px;' +
              (n.is_read ? '' : 'background:rgba(30,215,96,0.06);');
            div.textContent = n.message;
            notifList.appendChild(div);
          });
        }
      })['catch'](function(){});
  }

  // Poll for new notifications every 30s
  setInterval(fetchNotifs, 30000);
  setTimeout(fetchNotifs, 2000);

})();
