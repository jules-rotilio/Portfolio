import { Component } from '@angular/core';

interface School {
  years: string;
  title: string;
  place: string;
}

interface Experience {
  company: string;
  kind: 'Alternance' | 'Stage';
  period: string;
  place: string;
  missions: string[];
  technologies: string[];
}

interface SkillGroup {
  title: string;
  /** Nom de l'icône Bootstrap Icons, sans le préfixe « bi- ». */
  icon: string;
  items: string[];
}

@Component({
  selector: 'app-cv',
  imports: [],
  templateUrl: './cv.component.html',
  styleUrl: './cv.component.scss'
})
export class CVComponent {
  schools: School[] = [
    { years: '2024–25', title: 'Renforcement de compétences de développement', place: 'ORT · Lyon' },
    { years: '2023', title: 'Renforcement de compétences de développement', place: 'SUPINFO · Lyon' },
    { years: '2022', title: 'Licence Professionnelle ASSR — Cybersécurité', place: 'Auxerre' },
    { years: '2020–21', title: 'DUT Réseaux et Télécommunications', place: 'Auxerre' },
    { years: '2019', title: "Bac Scientifique — Sciences de l'ingénieur", place: 'Joigny' }
  ];

  experiences: Experience[] = [
    {
      company: 'Habitat et Humanisme',
      kind: 'Alternance',
      period: '2024 – 2025',
      place: 'Caluire-et-Cuire',
      missions: [
        "Projet de fusion de deux applications : développement d'un script Python pour la récupération des données.",
        "Mise en place d'une base de données PostgreSQL pour le stockage des données.",
        "Développement d'une interface web PHP pour la vérification manuelle de la fusion des données.",
        'Création de formulaires PowerApps et automatisations Power Automate.',
        "Développement d'un script C# puis PowerShell : compression, création de fichiers zip, envoi par email, upload via l'API SharePoint."
      ],
      technologies: ['Python', 'PostgreSQL', 'PHP', 'Power Platform', 'C#', 'PowerShell', 'SharePoint']
    },
    {
      company: 'Winciel',
      kind: 'Stage',
      period: '2023',
      place: 'Lyon',
      missions: [
        "Développement d'un script Bash de déploiement de l'ERP sur les serveurs Linux clients.",
        "Développement d'une interface en C# pour générer des étiquettes de transport sur une plateforme de logistique.",
        "Développement d'une solution de protection des serveurs en PowerShell et SQL pour bloquer les adresses IP des potentiels hackers."
      ],
      technologies: ['Bash', 'Linux', 'C#', 'PowerShell', 'SQL']
    },
    {
      company: "Conseil Départemental de l'Yonne",
      kind: 'Alternance',
      period: '2021 – 2022',
      place: 'Perrigny',
      missions: [
        "Veille des vulnérabilités via les publications de l'ANSSI et des journaux américains sur la sécurité informatique.",
        "Redécouverte d'un environnement informatique utilisant Active Directory : consultation et modification des informations des ordinateurs et utilisateurs.",
        "Développement d'un programme pour changer de réseau entre le réseau du Conseil Départemental et celui des collèges, facilitant le développement et le support téléphonique.",
        "Développement d'un script PowerShell pour prévenir par mail les utilisateurs AD de l'expiration de leur mot de passe.",
        "Gestion d'une solution d'emailing de prévention du phishing.",
        'Pentesting avec des outils de découverte de vulnérabilités et patch de serveurs vulnérables.'
      ],
      technologies: ['Veille sécurité', 'Active Directory', 'PowerShell', 'Pentesting', 'Anti-phishing']
    },
    {
      company: "Centre hospitalier d'Auxerre",
      kind: 'Stage',
      period: 'Avril – juin 2021',
      place: 'Auxerre',
      missions: [
        'Support téléphonique.',
        'Préparation de PC puis ajout automatique dans un domaine AD via SCCM.',
        "Écriture d'un script PowerShell de vérification des différents points de l'installation.",
        'Découverte du logiciel GLPI de gestion de tickets.'
      ],
      technologies: ['SCCM', 'Active Directory', 'PowerShell', 'GLPI']
    }
  ];

  skillGroups: SkillGroup[] = [
    {
      title: 'Langages',
      icon: 'code-slash',
      items: [
        'C# · .NET Core, ASP.NET Core',
        'SQL · PostgreSQL, MySQL, MariaDB',
        'PHP',
        'HTML, CSS',
        'JavaScript, TypeScript',
        'Python',
        'PowerShell',
        'Bash',
        'Dockerfile',
        'C++'
      ]
    },
    {
      title: 'Frameworks & connaissances',
      icon: 'stack',
      items: [
        'Entity Framework',
        'REST APIs',
        'Angular',
        '.NET WinForms',
        'ASP.NET MVC',
        'ASP.NET Web API',
        'Zend Framework MVC',
        'Flux RSS',
        'Certificats',
        'DNS'
      ]
    },
    {
      title: 'Outils',
      icon: 'tools',
      items: [
        'Visual Studio, VS Code',
        'Git, GitHub, GitLab',
        'MS Copilot, GitHub Copilot, Claude',
        'Docker',
        'Postman',
        'Jira, Trello',
        'Figma',
        'Burp Suite, Nmap',
        'Microsoft Office, Visio',
        'Linux (Ubuntu, Debian, Kali)',
        'Windows (Desktop, Server)'
      ]
    }
  ];

  languages = [
    { name: 'Français', level: 'Natif' },
    { name: 'Anglais', level: 'Courant et technique' }
  ];

  /** Sur téléphone, les missions sont repliables : seules celles de la première expérience sont ouvertes au départ. */
  private openMissions = new Set<number>([0]);

  isOpen(index: number): boolean {
    return this.openMissions.has(index);
  }

  toggleMissions(index: number): void {
    if (!this.openMissions.delete(index)) {
      this.openMissions.add(index);
    }
  }
}
