import { Component } from '@angular/core';
import { TabsModule } from 'carbon-components-angular';
@Component({
  selector: 'app-test',
  standalone: true,
  imports: [TabsModule],
  template: `
    <cds-tabs orientation="vertical">
      <cds-tab [heading]="myHeading">
        Content
      </cds-tab>
    </cds-tabs>
    <ng-template #myHeading><span>Hello</span></ng-template>
  `
})
export class TestComponent {}
