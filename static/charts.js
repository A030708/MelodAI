function renderUserGrowth(data) {
  const ctx = document.getElementById('userGrowthChart');
  if (!ctx) return;
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(d => d.date),
      datasets: [{
        label: 'New Users',
        data: data.map(d => d.count),
        borderColor: '#7c5cff',
        backgroundColor: 'rgba(124,92,255,0.1)',
        fill: true,
        tension: 0.3,
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxTicksLimit: 10, color: 'rgba(232,238,252,0.6)' } },
        y: { ticks: { color: 'rgba(232,238,252,0.6)' } }
      }
    }
  });
}

function renderTopSongs(data) {
  const ctx = document.getElementById('topSongsChart');
  if (!ctx) return;
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.title?.substring(0, 18)),
      datasets: [{
        label: 'Plays',
        data: data.map(d => d.plays),
        backgroundColor: 'rgba(124,92,255,0.6)',
        borderColor: '#7c5cff',
        borderWidth: 1,
      }]
    },
    options: {
      responsive: true,
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: 'rgba(232,238,252,0.6)' } },
        y: { ticks: { color: 'rgba(232,238,252,0.6)' } }
      }
    }
  });
}

function renderGenreDist(data) {
  const ctx = document.getElementById('genreChart');
  if (!ctx) return;
  const colors = ['#7c5cff', '#33d17a', '#ff5c7a', '#ffbe5c', '#5cbcff', '#ff85d4', '#85ffb8'];
  new Chart(ctx, {
    type: 'pie',
    data: {
      labels: data.map(d => d.genre),
      datasets: [{
        data: data.map(d => d.count),
        backgroundColor: colors.slice(0, data.length),
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: {
          position: 'right',
          labels: { color: 'rgba(232,238,252,0.6)' }
        }
      }
    }
  });
}

function renderActivity(data) {
  const feed = document.getElementById('activityFeed');
  if (!feed) return;
  feed.innerHTML = data.map(d =>
    `<div style="padding:6px 8px;border-radius:8px;background:rgba(255,255,255,0.03);margin-bottom:4px;font-size:12px;">
      <span class="chip" style="font-size:10px;padding:2px 6px;">${d.type}</span>
      <span style="margin-left:6px;">${d.user}</span>
      <span style="float:right;color:var(--muted2);font-size:11px;">${d.time?.substring(0,16)}</span>
    </div>`
  ).join('');
}

function renderEarningsChart(data) {
  const ctx = document.getElementById('earningsChart');
  if (!ctx) return;
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: (data || []).map(d => d.month),
      datasets: [{
        label: 'Earnings',
        data: (data || []).map(d => d.earnings),
        borderColor: '#1ed760',
        backgroundColor: 'rgba(30,215,96,0.1)',
        fill: true,
        tension: 0.3,
        pointBackgroundColor: '#1ed760',
        pointBorderColor: '#1ed760',
        pointRadius: 3,
        pointHoverRadius: 5,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: { maxTicksLimit: 8, color: '#b3b3b3', font: { family: 'SpotifyMixUI,Helvetica Neue,arial,sans-serif', size: 11 } },
          grid: { color: 'rgba(255,255,255,0.05)' }
        },
        y: {
          ticks: { color: '#b3b3b3', font: { family: 'SpotifyMixUI,Helvetica Neue,arial,sans-serif', size: 11 } },
          grid: { color: 'rgba(255,255,255,0.05)' }
        }
      }
    }
  });
}

function renderPerSongChart(data) {
  const ctx = document.getElementById('perSongChart');
  if (!ctx) return;
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: (data || []).map(d => d.title?.substring(0, 15)),
      datasets: [{
        label: 'Earnings',
        data: (data || []).map(d => d.earnings),
        backgroundColor: 'rgba(30,215,96,0.5)',
        borderColor: '#1ed760',
        borderWidth: 1,
        borderRadius: 3,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: { color: '#b3b3b3', font: { family: 'SpotifyMixUI,Helvetica Neue,arial,sans-serif', size: 11 } },
          grid: { color: 'rgba(255,255,255,0.05)' }
        },
        y: {
          ticks: { color: '#b3b3b3', font: { family: 'SpotifyMixUI,Helvetica Neue,arial,sans-serif', size: 11 } },
          grid: { display: false }
        }
      }
    }
  });
}
