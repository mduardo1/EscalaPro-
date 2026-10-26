'use strict';
const canvas = document.getElementById('weekly-chart');
if (canvas) {
  const values = JSON.parse(canvas.dataset.values);
  const labels = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
  if (window.Chart) {
    new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: '#2563EB',
          hoverBackgroundColor: '#1E40AF',
          borderRadius: 5,
          maxBarThickness: 29
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : {
          duration: 400
        },
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            callbacks: {
              label: context => `${context.parsed.y}h planejadas`
            }
          }
        },
        scales: {
          x: {
            grid: {
              display: false
            },
            border: {
              display: false
            },
            ticks: {
              color: '#94A0B1',
              font: {
                size: 10
              }
            }
          },
          y: {
            beginAtZero: true,
            suggestedMax: 8,
            border: {
              display: false
            },
            grid: {
              color: '#F0F3F8'
            },
            ticks: {
              maxTicksLimit: 5,
              color: '#A0ABBA',
              font: {
                size: 9
              },
              callback: value => `${value}h`
            }
          }
        }
      }
    });
  } else {
    // Sem acesso ao CDN, os mesmos dados continuam visíveis.
    canvas.hidden = true;
    const fallback = document.getElementById('chart-fallback');
    fallback.hidden = false;
    const maximum = Math.max(8, ...values);
    values.forEach((value, index) => {
      const day = document.createElement('div');
      day.className = 'fallback-day';
      const total = document.createElement('strong');
      total.textContent = `${value}h`;
      const bar = document.createElement('span');
      bar.className = 'fallback-bar';
      bar.style.height = `${value / maximum * 75}%`;
      const label = document.createElement('span');
      label.textContent = labels[index];
      day.append(total, bar, label);
      fallback.append(day);
    });
  }
}
