import { Component, Input, Output, EventEmitter } from '@angular/core';
import { HttpClient } from '@angular/common/http';

@Component({
  selector: 'app-user-card',
  template: `<button (click)="save()">Save</button>`,
})
export class UserCardComponent {
  @Input() name!: string;
  @Output() saved = new EventEmitter<void>();

  constructor(private http: HttpClient) {}

  save() {
    this.http.post('/api/users', { name: this.name }).subscribe(() => this.saved.emit());
  }
}
