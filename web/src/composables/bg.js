export async function applyBodyBg() {
  // 只在使用自定义背景时屏蔽随机 canvas
  const hasCustom = localStorage.getItem('has_custom_bg') === '1';
  const cbg = document.getElementById('cbg');
  if (hasCustom) {
    document.body.style.backgroundImage = "url('/api/util/background')";
    document.body.style.backgroundSize = 'cover';
    document.body.style.backgroundPosition = 'center';
    document.body.style.backgroundAttachment = 'fixed';
    if (cbg) cbg.style.display = 'none';
  } else {
    document.body.style.backgroundImage = '';
    if (cbg) cbg.style.display = '';
  }
}

export function resetBodyBg() {
  document.body.style.backgroundImage = '';
  const cbg = document.getElementById('cbg');
  if (cbg) cbg.style.display = '';
  localStorage.removeItem('has_custom_bg');
}
