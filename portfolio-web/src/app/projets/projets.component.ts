import { Component, OnInit } from '@angular/core';
import { ProjectsService } from '../services/projects.service';
import { NgFor } from '@angular/common';

@Component({
  selector: 'app-projets',
  imports: [NgFor],
  templateUrl: './projets.component.html',
  styleUrl: './projets.component.scss'
})
export class ProjetsComponent implements OnInit {
  projects: any[] = [];
  projectRows: any[][] = [];

  constructor(private projectsService: ProjectsService) {}

  ngOnInit(): void {
    //console.log('ProjetsComponent initialized'); // Ajoute ce log
    this.projectsService.getProjects().subscribe({
      next: (data) => {
        //console.log('Projects loaded:', data); // Ajoute ce log
        this.projects = data;
        this.projectRows = [];
        for (let i = 0; i < this.projects.length; i += 2) {
          this.projectRows.push(this.projects.slice(i, i + 2));
        }
      },
      error: (err) => console.error(err)
    });
  }
}
