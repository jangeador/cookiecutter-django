{%- if cookiecutter.frontend_pipeline == 'Webpack' -%}
import '../sass/project.scss';

{% endif -%}
{%- if cookiecutter.theme == 'Tailwind' %}
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('[data-nav-toggle]');
  const navigation = document.getElementById('main-navigation');
  if (toggle && navigation) {
    const mobile = window.matchMedia('(width < 48rem)');
    const updateNavigation = () => {
      const expanded = !mobile.matches;
      navigation.classList.toggle('hidden', !expanded);
      toggle.setAttribute('aria-expanded', String(expanded));
    };
    updateNavigation();
    mobile.addEventListener('change', updateNavigation);
    toggle.addEventListener('click', () => {
      const expanded = toggle.getAttribute('aria-expanded') !== 'true';
      navigation.classList.toggle('hidden', !expanded);
      toggle.setAttribute('aria-expanded', String(expanded));
    });
  }
  document.querySelectorAll('[data-dismiss-message]').forEach((button) => {
    button.addEventListener('click', () => button.closest('[role="status"]').remove());
  });
});
{%- endif %}

/* Project specific Javascript goes here. */
